"""
Bot de Telegram para Espia-negocios.
Uso: python telegram_bot.py
Comandos:
  /start     - Bienvenida
  /perfil <url> - Extrae negocios de un perfil de Google Maps
"""

import os
import time
import json
import urllib.request
import urllib.parse
import ssl
from maps_agent import extract_from_profile_url, format_result

# ── Configuración ──────────────────────────────────────────────────────────────
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8687984349:AAHsiQCtx-XVLR0KjOj509zoagRCD0VRjdI")
ALLOWED_USER = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "8601500155")
SHEETS_WEBHOOK = os.environ.get("SHEETS_WEBHOOK_URL", "https://script.google.com/macros/s/AKfycbxM6Gw4QKe-M_J_HqEP2PXxT2xydiaKWypZZMoeKQOnwgiWUNabJOsCoPkPTq2vgydN/exec")

API = f"https://api.telegram.org/bot{TOKEN}"
ctx = ssl.create_default_context()


# ── Helpers de la API de Telegram ──────────────────────────────────────────────
def _api(method, payload=None):
    url = f"{API}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    timeout = 90 if method == "getUpdates" else 20
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[API error] {method}: {e}")
        return {}


def send(chat_id, text, parse_mode="Markdown"):
    _api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": parse_mode})


def send_to_sheets(biz):
    if not SHEETS_WEBHOOK:
        return
    data = json.dumps(biz).encode()
    req = urllib.request.Request(
        SHEETS_WEBHOOK, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req, context=ctx, timeout=10)
    except Exception as e:
        print(f"[Sheets error] {e}")


# ── Lógica de mensajes ─────────────────────────────────────────────────────────
def handle_message(msg):
    chat_id = str(msg.get("chat", {}).get("id", ""))
    user_id = str(msg.get("from", {}).get("id", ""))
    text = msg.get("text", "").strip()

    # Seguridad: solo tu usuario
    if ALLOWED_USER and user_id != ALLOWED_USER:
        send(chat_id, "⛔ No tienes permiso para usar este bot.")
        return

    if text == "/start":
        send(chat_id, (
            "👋 *Espia-negocios* listo\\.\n\n"
            "Envíame un perfil de Google Maps y extraeré los negocios reseñados:\n\n"
            "`/perfil https://www.google.com/maps/contrib/...`"
        ), parse_mode="MarkdownV2")

    elif text.startswith("/perfil"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send(chat_id, "Usa: `/perfil <url>`")
            return
        url = parts[1].strip()
        send(chat_id, "🔍 Buscando negocios, un momento...")
        negocios = extract_from_profile_url(url)
        for biz in negocios:
            send(chat_id, format_result(biz))
            if "error" not in biz:
                send_to_sheets(biz)
        send(chat_id, f"✅ Listo — {len([b for b in negocios if 'error' not in b])} negocio(s) procesado(s).")

    else:
        # Si mandan una URL directamente sin comando
        if text.startswith("http") and "google.com/maps" in text:
            send(chat_id, "🔍 Detecté un enlace de Google Maps, buscando negocios...")
            negocios = extract_from_profile_url(text)
            for biz in negocios:
                send(chat_id, format_result(biz))
                if "error" not in biz:
                    send_to_sheets(biz)
            send(chat_id, f"✅ Listo — {len([b for b in negocios if 'error' not in b])} negocio(s) procesado(s).")
        else:
            send(chat_id, "Envía `/perfil <url>` o pega directamente un enlace de Google Maps.")


# ── Polling ────────────────────────────────────────────────────────────────────
def run():
    print(f"[Bot] Iniciando polling... (usuario permitido: {ALLOWED_USER})")
    offset = 0
    while True:
        try:
            resp = _api("getUpdates", {"offset": offset, "timeout": 60})
            for update in resp.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
        except KeyboardInterrupt:
            print("[Bot] Detenido.")
            break
        except Exception as e:
            print(f"[Bot] Error en polling: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run()
