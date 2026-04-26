import urllib.request
import urllib.parse
import re
import json
import ssl

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ctx = ssl.create_default_context()


def _fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None


def _extract_place_ids(html):
    """Extrae IDs de lugares de un perfil de contribuidor."""
    return re.findall(r'"(0x[0-9a-fA-F]+:[0-9a-fA-F]+)"', html)


def _extract_business_info_from_html(html, url=""):
    info = {
        "nombre": "",
        "telefono": "",
        "email": "",
        "web": "",
        "direccion": "",
        "url_origen": url,
    }

    # Nombre
    for pattern in [
        r'"name"\s*:\s*"([^"]{3,80})"',
        r'<title>([^<]{3,80})</title>',
        r'aria-label="([^"]{3,80})"',
    ]:
        m = re.search(pattern, html)
        if m:
            info["nombre"] = m.group(1).strip()
            break

    # Teléfono
    tel = re.search(r'(\+?[\d\s\-\(\)]{9,16})', html)
    if tel:
        info["telefono"] = tel.group(1).strip()

    # Web
    web = re.search(r'https?://(?!maps\.google|google\.com|goo\.gl)[^\s"\'<>]{5,}', html)
    if web:
        info["web"] = web.group(0).strip()

    # Email (a veces aparece en la web del negocio)
    email = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
    if email and "google" not in email.group(0):
        info["email"] = email.group(0)

    # Dirección
    addr = re.search(r'"address"\s*:\s*"([^"]{5,})"', html)
    if addr:
        info["direccion"] = addr.group(1)

    return info


def _try_fetch_email_from_web(web_url):
    """Intenta encontrar email en la web del negocio."""
    if not web_url:
        return ""
    html = _fetch(web_url)
    if not html:
        return ""
    email = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
    if email and not any(x in email.group(0) for x in ["google", "example", "sentry", "pixel"]):
        return email.group(0)
    return ""


def extract_from_profile_url(url):
    """
    Recibe una URL de perfil de contribuidor de Google Maps y devuelve
    una lista de dicts con info de los negocios reseñados.
    """
    results = []
    html = _fetch(url)
    if not html:
        return [{"error": "No se pudo acceder a la URL (posible bloqueo de Google)"}]

    # Buscar bloques de datos de negocios en el HTML
    # Google Maps embebe datos JSON en el HTML
    place_blocks = re.findall(r'\["([^"]{3,80})",[^]]*?"(\+?[\d\s\-\(\)]{9,16})"', html)

    seen = set()
    for block in place_blocks:
        nombre = block[0].strip()
        telefono = block[1].strip()
        if nombre in seen:
            continue
        seen.add(nombre)
        results.append({
            "nombre": nombre,
            "telefono": telefono,
            "email": "",
            "web": "",
            "direccion": "",
            "url_origen": url,
        })

    # Si no encontramos nada estructurado, intentamos extracción genérica
    if not results:
        info = _extract_business_info_from_html(html, url)
        if info["nombre"]:
            results.append(info)

    # Intentar enriquecer con email desde la web del negocio
    for r in results:
        if r.get("web") and not r.get("email"):
            r["email"] = _try_fetch_email_from_web(r["web"])

    if not results:
        return [{"error": "No se encontraron negocios en este perfil. Google Maps puede estar bloqueando el acceso."}]

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
    return "\n".join(lines) if lines else "Sin datos encontrados"
