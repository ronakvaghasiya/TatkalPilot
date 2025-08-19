# TatkalFlow  Booking (n8n + Python Selenium)

> Legal & safe helper. **No captcha auto-solve or policy bypass.** Captcha is relayed to you via Telegram, you reply `/cap <session> <text>` and the script fills it.

## Components
- **Python** (`Flask`, `Selenium`) runs a small server on `http://localhost:5000`
- **n8n** handles reminders, Telegram messages, and captcha relay

## Files
- `app.py` — Flask server: `/start-booking`, `/captcha-answer`, `/health`
- `booking_engine.py` — Selenium logic, opens IRCTC, captures captcha, fills basic fields
- `n8n_workflow.json` — Import into n8n
- `requirements.txt`
- `config.sample.env` — copy to `.env` and set values

## Setup
1. **Python env**
   ```bash
   cd TatkalFlow 
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp config.sample.env .env
   ```

2. **Run server**
   ```bash
   python app.py
   ```

3. **n8n**
   - Create credentials for **Telegram** bot.
   - Set environment variables in n8n:
     - `TELEGRAM_CRED_ID` → the credential ID (or re-wire the Telegram nodes)
     - `TELEGRAM_CHAT_ID` → your chat/group id
   - Import `n8n_workflow.json` (top-right → Import from file).
   - Copy each webhook URL shown by n8n and set in your environment or `.env`:
     - `N8N_CAPTCHA_IN_WEBHOOK_URL`
     - `N8N_BOOKING_STATUS_WEBHOOK_URL`
   - Activate the workflow.

## Usage
- Start booking by sending a POST to n8n webhook `/start-booking` **or** Execute Webhook node.
- Sample body:
  ```json
  {
    "session_id": "rv-2025-08-19-01",
    "login": {"username": "", "password": ""},
    "journey": {"from": "AHMEDABAD JN", "to": "NEW DELHI", "date": "2025-08-20"},
    "passengers": [
      {"name":"R Vaghasiya","age":28,"gender":"M","berth_pref":"LB","id_type":"AADHAAR","id_no":""}
    ]
  }
  ```
- Python opens IRCTC, sends captcha to Telegram via n8n.
- Reply: `/cap rv-2025-08-19-01 A1B2C`

## Notes
- IRCTC UI changes frequently; selectors are best-effort. Keep Chrome updated.
- This helper pauses before train selection/payment to stay within policy.
- Extend selectors in `booking_engine.py` if UI updates.

