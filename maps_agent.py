import re
import json

def _extract_businesses_from_html(html):
    """Extrae negocios del HTML renderizado de Google Maps."""
    results = []

    # Google Maps embebe los datos en bloques JSON dentro del HTML
    # Buscamos patrones de nombre + dirección que aparecen en perfiles de contribuidor

    # Patrón: bloques de reseñas con nombre del negocio y dirección
    blocks = re.findall(
        r'"([^"]{3,80})"\s*,\s*"([^"]*(?:calle|c\.|av\.|plaza|paseo|cami)[^"]*)"',
        html, re.IGNORECASE
    )

    # Patrón alternativo: buscar nombres de negocios cerca de coordenadas o ratings
    names = re.findall(r'class="[^"]*fontHeadlineSmall[^"]*"[^>]*>([^<]{3,60})<', html)
    addresses = re.findall(r'class="[^"]*fontBodyMedium[^"]*"[^>]*>([^<]{5,100})<', html)

    seen = set()

    # Intentar extraer del JSON embebido (window.__initData o similar)
    json_blobs = re.findall(r'\[\s*"([^"]{3,80})"\s*,\s*null\s*,\s*\[\s*\[\s*null\s*,\s*"([^"]{5,})"', html)
    for blob in json_blobs:
        nombre = blob[0].strip()
        direccion = blob[1].strip()
        if nombre not in seen and len(nombre) > 2:
            seen.add(nombre)
            results.append({
                "nombre": nombre,
                "direccion": direccion,
                "telefono": "",
                "email": "",
                "web": "",
            })

    for name in names:
        name = name.strip()
        if name and name not in seen and len(name) > 2:
            seen.add(name)
            results.append({
                "nombre": name,
                "direccion": "",
                "telefono": "",
                "email": "",
                "web": "",
            })

    return results


def extract_from_profile_url(url):
    """
    Usa Playwright para renderizar el perfil y extraer los negocios reseñados.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [{"error": "Playwright no instalado. Ejecuta: pip install playwright && playwright install chromium"}]

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-ES"
        )
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Extraer tarjetas de reseñas — cada reseña tiene el nombre del negocio
            cards = page.query_selector_all('[data-review-id], [jsaction*="review"], .jftiEf, .WMbnJf')

            seen = set()
            for card in cards:
                nombre = ""
                direccion = ""
                telefono = ""

                # Nombre del negocio
                for sel in ['.OSrXXb', '.fontHeadlineSmall', 'a[href*="maps/place"]', '.kvMYJc']:
                    el = card.query_selector(sel)
                    if el:
                        t = el.inner_text().strip()
                        if t and len(t) > 2:
                            nombre = t
                            break

                # Si no encontramos en la tarjeta, buscar enlace al lugar
                if not nombre:
                    link = card.query_selector('a[href*="/maps/place/"]')
                    if link:
                        href = link.get_attribute('href') or ''
                        m = re.search(r'/maps/place/([^/@]+)', href)
                        if m:
                            nombre = urllib_unquote(m.group(1).replace('+', ' '))

                # Dirección
                for sel in ['.fontBodyMedium', '.Io6YTe', '.rogA2c']:
                    el = card.query_selector(sel)
                    if el:
                        t = el.inner_text().strip()
                        if t and len(t) > 5:
                            direccion = t
                            break

                if nombre and nombre not in seen:
                    seen.add(nombre)
                    results.append({
                        "nombre": nombre,
                        "direccion": direccion,
                        "telefono": telefono,
                        "email": "",
                        "web": "",
                        "url_origen": url,
                    })

            # Si no encontramos con selectores específicos, intentar con el HTML
            if not results:
                html = page.content()
                results = _extract_businesses_from_html(html)
                for r in results:
                    r["url_origen"] = url

            # Para cada negocio, intentar obtener teléfono visitando su página
            for biz in results[:10]:  # límite de 10 para no tardar demasiado
                nombre_enc = biz["nombre"].replace(" ", "+")
                search_url = f"https://www.google.com/maps/search/{nombre_enc}"
                try:
                    page.goto(search_url, wait_until="networkidle", timeout=15000)
                    page.wait_for_timeout(2000)
                    # Teléfono
                    for sel in ['[data-item-id*="phone"] .Io6YTe', 'button[data-item-id*="phone"] .rogA2c', '[aria-label*="eléfono"]']:
                        el = page.query_selector(sel)
                        if el:
                            biz["telefono"] = el.inner_text().strip()
                            break
                    # Web
                    for sel in ['a[data-item-id*="authority"]', 'a[href*="http"][aria-label*="eb"]']:
                        el = page.query_selector(sel)
                        if el:
                            biz["web"] = el.get_attribute("href") or ""
                            break
                except Exception:
                    pass

        finally:
            browser.close()

    if not results:
        return [{"error": "No se encontraron negocios. Google Maps puede haber cambiado su estructura."}]

    return results


def urllib_unquote(s):
    try:
        from urllib.parse import unquote
        return unquote(s)
    except Exception:
        return s


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
    return "\n".join(lines) if lines else "Sin datos encontrados"
