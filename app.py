\
import os
from flask import Flask, request, jsonify
from booking_engine import TatkalBooker

app = Flask(__name__)

CAPTCHA_STORE = {}
SESSION_STATUS = {}

def get_captcha_text(session_id: str):
    return CAPTCHA_STORE.get(session_id)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/captcha-answer")
def captcha_answer():
    data = request.get_json(force=True, silent=True) or request.form
    session_id = data.get("session_id")
    captcha_text = data.get("captcha_text")
    if not session_id or not captcha_text:
        return {"ok": False, "error": "session_id and captcha_text required"}, 400
    CAPTCHA_STORE[session_id] = captcha_text
    SESSION_STATUS.setdefault(session_id, []).append({"event": "captcha_answer_received"})
    return {"ok": True}

@app.post("/start-booking")
def start_booking():
    payload = request.get_json(force=True)
    session_id = payload.get("session_id")
    if not session_id:
        return {"ok": False, "error": "session_id required"}, 400

    n8n_captcha_in = os.getenv("N8N_CAPTCHA_IN_WEBHOOK_URL", "http://localhost:5678/webhook/captcha-in")
    n8n_status = os.getenv("N8N_BOOKING_STATUS_WEBHOOK_URL", "http://localhost:5678/webhook/booking-status")

    def worker():
        try:
            be = TatkalBooker(session_id=session_id, n8n_captcha_in_url=n8n_captcha_in, n8n_status_url=n8n_status)
            be.run(login=payload.get("login", {}),
                   journey=payload.get("journey", {}),
                   passengers=payload.get("passengers", []))
        except Exception as e:
            import requests
            try:
                requests.post(n8n_status, json={"session_id": session_id, "event": "error", "error": str(e)}, timeout=15)
            except Exception:
                pass

    import threading
    t = threading.Thread(target=worker, daemon=True)
    t.start()

    return {"ok": True, "session_id": session_id}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
