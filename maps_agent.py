import re
from urllib.parse import unquote


def extract_from_profile_url(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [{"error": "Playwright no instalado. Ejecuta: pip install playwright && playwright install chromium"}]

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-ES"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(4000)

            # Scroll para cargar todas las reseñas
            for _ in range(5):
                page.keyboard.press("End")
                page.wait_for_timeout(1000)

            # Buscar todos los enlaces a negocios (/maps/place/)
            links = page.eval_on_selector_all(
                'a[href*="/maps/place/"]',
                'els => els.map(e => ({ href: e.href, text: e.innerText.trim() }))'
            )

            seen_hrefs = set()
            place_urls = []
            for link in links:
                href = link.get("href", "")
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    # Extraer nombre del negocio de la URL
                    m = re.search(r'/maps/place/([^/@?]+)', href)
                    nombre = unquote(m.group(1).replace('+', ' ')) if m else link.get("text", "")
                    if nombre and len(nombre) > 2:
                        place_urls.append({"nombre": nombre, "href": href})

            print(f"[Agent] Encontrados {len(place_urls)} negocios en el perfil")

            # Visitar cada negocio para sacar teléfono, web, email
            for place in place_urls[:20]:
                biz = {
                    "nombre": place["nombre"],
                    "telefono": "",
                    "email": "",
                    "web": "",
                    "direccion": "",
                    "url_origen": url,
                }

                try:
                    page.goto(place["href"], wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(2000)

                    # Nombre real (más limpio que el de la URL)
                    for sel in ['h1.DUwDvf', 'h1[class*="fontHeadline"]', 'h1']:
                        el = page.query_selector(sel)
                        if el:
                            t = el.inner_text().strip()
                            if t:
                                biz["nombre"] = t
                                break

                    # Teléfono
                    tel_el = page.query_selector('[data-item-id*="phone:tel"] .rogA2c, [data-item-id*="phone:tel"] .Io6YTe')
                    if tel_el:
                        biz["telefono"] = tel_el.inner_text().strip()
                    else:
                        # Buscar por aria-label
                        tel_btn = page.query_selector('button[aria-label*="eléfono"], button[aria-label*="hone"]')
                        if tel_btn:
                            label = tel_btn.get_attribute("aria-label") or ""
                            m = re.search(r'[\+\d][\d\s\-\(\)]{7,}', label)
                            if m:
                                biz["telefono"] = m.group(0).strip()

                    # Dirección
                    addr_el = page.query_selector('[data-item-id*="address"] .rogA2c, [data-item-id*="address"] .Io6YTe')
                    if addr_el:
                        biz["direccion"] = addr_el.inner_text().strip()

                    # Web
                    web_el = page.query_selector('a[data-item-id*="authority"], a[aria-label*="Sitio web"], a[aria-label*="web"]')
                    if web_el:
                        biz["web"] = web_el.get_attribute("href") or ""

                    # Email: buscar en la web del negocio
                    if biz["web"] and not biz["email"]:
                        try:
                            page.goto(biz["web"], wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(1500)
                            content = page.content()
                            em = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', content)
                            if em and not any(x in em.group(0) for x in ["google", "example", "sentry", "schema", "pixel", "wix"]):
                                biz["email"] = em.group(0)
                        except Exception:
                            pass

                except Exception as e:
                    print(f"[Agent] Error visitando {place['nombre']}: {e}")

                results.append(biz)
                print(f"[Agent] ✓ {biz['nombre']} | Tel: {biz['telefono']} | Email: {biz['email']}")

        finally:
            browser.close()

    if not results:
        return [{"error": "No se encontraron negocios. Puede que Google haya bloqueado el acceso."}]

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
