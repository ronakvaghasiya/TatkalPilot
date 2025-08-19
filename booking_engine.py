\
import os
import time
import requests
from typing import Dict, Any, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

IRCTC_URL = "https://www.irctc.co.in/nget/train-search"

def _bool_env(name: str, default: bool=False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1","true","yes","y","on")

class TatkalBooker:
    """
    Booking engine that:
      - opens IRCTC
      - logs in (username/password optional)
      - captures captcha image and asks user via n8n->Telegram
      - fills journey + passengers (skeleton with safe selectors)
      - notifies n8n about status updates
    """
    def __init__(self, session_id: str, n8n_captcha_in_url: str, n8n_status_url: str):
        self.session_id = session_id
        self.n8n_captcha_in_url = n8n_captcha_in_url
        self.n8n_status_url = n8n_status_url
        self._driver = None

    # ---------- browser setup ----------
    def _driver_start(self):
        opts = Options()
        if _bool_env("HEADLESS", False):
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--window-size=1280,900")
        self._driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=opts)

    def _driver_quit(self):
        if self._driver:
            self._driver.quit()
            self._driver = None

    # ---------- n8n notify helpers ----------
    def _notify(self, payload: Dict[str, Any]):
        payload = {"session_id": self.session_id, **payload}
        try:
            requests.post(self.n8n_status_url, json=payload, timeout=15)
        except Exception as e:
            print("Status notify failed:", e)

    def _send_captcha_image(self, png_bytes: bytes):
        files = {"captcha": ("captcha.png", png_bytes, "image/png")}
        data = {"session_id": self.session_id}
        try:
            requests.post(self.n8n_captcha_in_url, data=data, files=files, timeout=30)
        except Exception as e:
            print("Captcha relay failed:", e)

    # ---------- core steps ----------
    def _login(self, username: Optional[str], password: Optional[str]) -> None:
        d = self._driver
        self._notify({"event": "nav", "msg": "Opening IRCTC login"})
        d.get(IRCTC_URL)
        time.sleep(2.5)

        # Click the Login button to open modal
        try:
            login_btn = d.find_element(By.XPATH, "//a[contains(., 'LOGIN') or contains(@aria-label,'Login')]")
            login_btn.click()
            time.sleep(2)
        except Exception:
            pass

        # Attempt to locate fields (IRCTC updates selectors occasionally)
        user_candidates = [
            (By.ID, "userId"),
            (By.CSS_SELECTOR, "input[formcontrolname='userid']"),
            (By.XPATH, "//input[contains(@placeholder,'User Name') or contains(@aria-label,'User Name')]"),
        ]
        pass_candidates = [
            (By.ID, "pwd"),
            (By.CSS_SELECTOR, "input[formcontrolname='password']"),
            (By.XPATH, "//input[@type='password']"),
        ]

        def _fill_first(cands, value):
            for by, sel in cands:
                try:
                    el = d.find_element(by, sel)
                    el.clear()
                    el.send_keys(value)
                    return True
                except Exception:
                    continue
            return False

        if username:
            _fill_first(user_candidates, username)
        if password:
            _fill_first(pass_candidates, password)

        # Find captcha img
        captcha_img = None
        for by, sel in [
            (By.CSS_SELECTOR, "img.captcha-img"),
            (By.CSS_SELECTOR, "img[aria-label*='captcha' i]"),
            (By.XPATH, "//img[contains(@src,'captcha') or contains(@alt,'captcha')]"),
        ]:
            try:
                captcha_img = d.find_element(by, sel)
                break
            except Exception:
                continue

        if captcha_img is None:
            self._notify({"event": "captcha_missing", "msg": "Captcha image not found. Enter manually."})
        else:
            png = captcha_img.screenshot_as_png
            self._send_captcha_image(png)
            self._notify({"event": "captcha_sent", "msg": "Captcha sent to Telegram. Reply with /cap <session> <text>."})

        # Wait for captcha text via Flask store (set by n8n call)
        from app import get_captcha_text  # local import
        import time as _t
        start = _t.time()
        captcha_text = None
        while _t.time() - start < 120:
            captcha_text = get_captcha_text(self.session_id)
            if captcha_text:
                break
            _t.sleep(1)

        if not captcha_text:
            self._notify({"event": "captcha_timeout", "error": "No captcha received in time."})
            raise RuntimeError("Captcha timeout")

        # Fill captcha and submit
        for by, sel in [
            (By.ID, "captcha"),
            (By.CSS_SELECTOR, "input[formcontrolname='captcha']"),
            (By.XPATH, "//input[contains(@placeholder,'Enter Captcha') or contains(@aria-label,'Captcha')]"),
        ]:
            try:
                el = d.find_element(by, sel)
                el.clear()
                el.send_keys(captcha_text)
                break
            except Exception:
                continue

        for by, sel in [
            (By.ID, "loginBtn"),
            (By.XPATH, "//button[contains(.,'SIGN IN') or contains(.,'Login') or contains(@aria-label,'Sign in')]"),
            (By.CSS_SELECTOR, "button[type='submit']"),
        ]:
            try:
                d.find_element(by, sel).click()
                break
            except Exception:
                continue

        self._notify({"event": "login_submitted"})
        time.sleep(4)

    def _fill_journey_details(self, details: Dict[str, Any]):
        d = self._driver
        self._notify({"event": "journey_fill_start"})
        time.sleep(0.8)

        # From station
        for by, sel in [
            (By.CSS_SELECTOR, "input[placeholder*='From' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='From' i]"),
        ]:
            try:
                el = d.find_element(by, sel)
                el.clear()
                el.send_keys(details.get("from", ""))
                time.sleep(0.5)
                el.click()
                break
            except Exception:
                continue

        # To station
        for by, sel in [
            (By.CSS_SELECTOR, "input[placeholder*='To' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='To' i]"),
        ]:
            try:
                el = d.find_element(by, sel)
                el.clear()
                el.send_keys(details.get("to", ""))
                time.sleep(0.5)
                el.click()
                break
            except Exception:
                continue

        self._notify({"event": "verify_date_quota", "msg": "Verify journey date and set Quota=Tatkal, then press Search."})

    def _simulate_passenger_fill(self, passengers: List[Dict[str, Any]]):
        self._notify({"event": "passengers_loaded", "count": len(passengers)})

    def run(self, login: Dict[str, str], journey: Dict[str, Any], passengers: List[Dict[str, Any]]):
        try:
            self._driver_start()
            self._login(login.get("username") or os.getenv("IRCTC_USERNAME"), login.get("password") or os.getenv("IRCTC_PASSWORD"))
            self._fill_journey_details(journey)
            self._simulate_passenger_fill(passengers)
            self._notify({"event": "hand_off", "msg": "Proceed with train selection & payment (manual)."})
        finally:
            time.sleep(120)
            self._driver_quit()
