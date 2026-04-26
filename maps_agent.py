import re
import json
from urllib.parse import unquote


def _parse_google_json(text):
    """Extrae datos de negocio del JSON que devuelve Google Maps internamente."""
    businesses = []
    seen = set()

    # Google devuelve datos en formato )]}'  seguido de JSON
    text = re.sub(r"^\)\]}'", "", text.strip())

    # Buscar patrones: nombre de negocio + teléfono en el blob JSON
    # Los teléfonos suelen aparecer como "+34 XXX XXX XXX" o "XXX XXX XXX"
    phones = re.findall(r'"\+?[\d][\d\s\-]{8,15}"', text)
    names_raw = re.findall(r'"([A-ZÁÉÍÓÚÑ][^"]{2,50}(?:S\.L\.|S\.A\.|SL|SA|bar|café|hotel|clínica|inmobili[^"]*)?)"', text, re.IGNORECASE)

    # Mejor enfoque: buscar bloques que contengan nombre + dirección juntos
    # Patrón típico en el JSON de Google: ["Nombre del negocio", null, ["Calle...", ...]]
    blocks = re.findall(
        r'\["([^"]{3,60})",null,\[(?:null,)?\["([^"]{5,100})"',
        text
    )
    for b in blocks:
        nombre, direccion = b
        if nombre not in seen and not nombre.startswith("http"):
            seen.add(nombre)
            businesses.append({
                "nombre": nombre,
                "direccion": direccion,
                "telefono": "",
                "email": "",
                "web": "",
            })

    return businesses


def extract_from_profile_url(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [{"error": "Playwright no instalado. Ejecuta: pip install playwright && playwright install chromium"}]

    captured_responses = []
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        # Interceptar respuestas de la API interna de Google Maps
        def handle_response(response):
            r_url = response.url
            if any(x in r_url for x in ["maps/preview/place", "maps/api/place", "maps/rpc", "listugcposts", "GetReviews", "contrib"]):
                try:
                    body = response.text()
                    if body and len(body) > 100:
                        captured_responses.append(body)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(5000)

            # Scroll para forzar carga de más reseñas
            for _ in range(8):
                page.keyboard.press("End")
                page.wait_for_timeout(800)

            page.wait_for_timeout(2000)

            # Estrategia 1: extraer del HTML completo renderizado
            html = page.content()

            # Buscar todos los enlaces a negocios en el HTML renderizado
            place_links = re.findall(r'href="(https://www\.google\.com/maps/place/[^"]+)"', html)
            place_links += re.findall(r'href="(/maps/place/[^"]+)"', html)

            seen = set()
            place_data = []
            for link in place_links:
                if link.startswith("/"):
                    link = "https://www.google.com" + link
                m = re.search(r'/maps/place/([^/@?&]+)', link)
                if m:
                    nombre = unquote(m.group(1).replace('+', ' '))
                    clean_link = re.sub(r'(?<=\d{10,})/.*', '', link)  # normalizar URL
                    if nombre not in seen and len(nombre) > 2 and not nombre.startswith("0x"):
                        seen.add(nombre)
                        place_data.append({"nombre": nombre, "href": link})

            print(f"[Agent] {len(place_data)} negocios encontrados en el perfil")

            # Estrategia 2: si no hay enlaces, parsear respuestas capturadas
            if not place_data:
                for resp_text in captured_responses:
                    businesses = _parse_google_json(resp_text)
                    for biz in businesses:
                        if biz["nombre"] not in seen:
                            seen.add(biz["nombre"])
                            place_data.append({"nombre": biz["nombre"], "href": "", "direccion": biz.get("direccion", "")})

            # Visitar cada página de negocio para obtener teléfono, web, email
            for place in place_data[:20]:
                biz = {
                    "nombre": place["nombre"],
                    "telefono": "",
                    "email": "",
                    "web": "",
                    "direccion": place.get("direccion", ""),
                    "url_origen": url,
                }

                if not place.get("href"):
                    results.append(biz)
                    continue

                try:
                    page.goto(place["href"], wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(2000)

                    # Nombre real desde la página del negocio
                    h1 = page.query_selector('h1')
                    if h1:
                        t = h1.inner_text().strip()
                        if t and len(t) > 1:
                            biz["nombre"] = t

                    # Extraer del HTML de la página del negocio
                    biz_html = page.content()

                    # Teléfono: buscar en atributos aria-label y en el HTML
                    tel_patterns = [
                        r'aria-label="Teléfono:\s*([\+\d\s\-\(\)]{9,20})"',
                        r'aria-label="Phone:\s*([\+\d\s\-\(\)]{9,20})"',
                        r'"phone:tel:([\+\d\s\-\(\)]{9,20})"',
                        r'\+34\s*[\d\s]{9,12}',
                        r'(?<!\d)[\d]{3}[\s\-]?[\d]{3}[\s\-]?[\d]{3}(?!\d)',
                    ]
                    for pat in tel_patterns:
                        m = re.search(pat, biz_html)
                        if m:
                            biz["telefono"] = m.group(1).strip() if m.lastindex else m.group(0).strip()
                            break

                    # Dirección
                    addr_m = re.search(r'aria-label="Dirección:\s*([^"]{5,100})"', biz_html)
                    if addr_m:
                        biz["direccion"] = addr_m.group(1).strip()

                    # Web
                    web_m = re.search(r'aria-label="Sitio web[^"]*"\s+href="([^"]+)"', biz_html)
                    if not web_m:
                        web_m = re.search(r'href="(https?://(?!google|goo\.gl|maps)[^"]{5,})"[^>]*aria-label="[^"]*[Ww]eb', biz_html)
                    if web_m:
                        biz["web"] = web_m.group(1)

                    # Email desde la web del negocio
                    if biz["web"]:
                        try:
                            page.goto(biz["web"], wait_until="domcontentloaded", timeout=12000)
                            page.wait_for_timeout(1500)
                            web_content = page.content()
                            em = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', web_content)
                            if em:
                                candidate = em.group(0)
                                if not any(x in candidate.lower() for x in ["google", "example", "sentry", "schema", "pixel", "wix", "jquery"]):
                                    biz["email"] = candidate
                        except Exception:
                            pass

                except Exception as e:
                    print(f"[Agent] Error en {place['nombre']}: {e}")

                results.append(biz)
                print(f"[Agent] ✓ {biz['nombre']} | {biz['telefono']} | {biz['email']}")

        finally:
            browser.close()

    if not results:
        return [{"error": "No se encontraron negocios. Prueba con otro enlace de perfil."}]

    return results


def format_result(biz):
    if "error" in biz:
        return f"⚠️ {biz['error']}"
    lines = []
    if biz.get("nombre"):
        lines.append(f"🏢 *{biz['nombre']}*")
    if biz.get("telefono"):
        lines.append(f"📞 {biz['telefono']}")
    if biz.get("email"):
        lines.append(f"📧 {biz['email']}")
    if biz.get("web"):
        lines.append(f"🌐 {biz['web']}")
    if biz.get("direccion"):
        lines.append(f"📍 {biz['direccion']}")
    return "\n".join(lines) if lines else "⚠️ Sin datos encontrados"
