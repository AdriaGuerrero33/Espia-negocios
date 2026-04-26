# Espia-negocios

Agente que extrae nombre, teléfono, email y web de negocios a partir de perfiles de Google Maps, con bot de Telegram y exportación a Google Sheets.

## Uso rápido

```bash
# 1. Clona y entra al proyecto
git clone https://github.com/AdriaGuerrero33/Espia-negocios.git
cd Espia-negocios

# 2. Configura variables (opcional, ya tiene valores por defecto)
cp .env.example .env
# Edita .env con tu token y webhook de Sheets

# 3. Arranca el bot
python telegram_bot.py
```

## Comandos en Telegram

| Comando | Descripción |
|---|---|
| `/start` | Bienvenida |
| `/perfil <url>` | Extrae negocios de un perfil de contribuidor |
| Pegar URL directamente | También funciona sin comando |

## Google Sheets (opcional)

1. Crea una hoja en Google Sheets
2. Ve a **Extensiones → Apps Script** y pega:

```javascript
function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var data = JSON.parse(e.postData.contents);
  sheet.appendRow([
    new Date(),
    data.nombre || '',
    data.telefono || '',
    data.email || '',
    data.web || '',
    data.direccion || '',
    data.url_origen || ''
  ]);
  return ContentService.createTextOutput('OK');
}
```

3. **Implementar → Nueva implementación → Aplicación web**
   - Ejecutar como: Yo
   - Acceso: Cualquier persona
4. Copia la URL y ponla en `.env` como `SHEETS_WEBHOOK_URL`

## Variables de entorno

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot de BotFather |
| `TELEGRAM_ALLOWED_USER_ID` | Tu ID de Telegram (solo tú puedes usar el bot) |
| `SHEETS_WEBHOOK_URL` | URL del webhook de Apps Script (opcional) |
