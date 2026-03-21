"""
Mindbody automatikus időpontfoglaló
"""
import os, sys, time, json, logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

BASE    = "https://clients.mindbodyonline.com"
STUDIO  = os.environ["MB_STUDIO_ID"]        # pl. 48016
EMAIL   = os.environ["MB_EMAIL"]
PASSWD  = os.environ["MB_PASSWORD"]
INSTR   = os.environ["MB_INSTRUCTOR"]       # pl. "Ujvári Cili"
CLASS   = os.environ["MB_CLASS"]            # pl. "TRX köredzés"
DATE    = os.environ["MB_CLASS_DATE"]       # pl. "3/30/2026"
LOC     = os.environ.get("MB_LOCATION", "2")
TG      = os.environ.get("MB_TG", "23")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
}

def login(s: requests.Session) -> bool:
    url = f"{BASE}/Login?studioID={STUDIO}&isLibAsync=true&isJson=true"
    data = {
        "requiredtxtUserName": EMAIL,
        "requiredtxtPassword": PASSWD,
        "tg": "", "vt": "", "lvl": "", "stype": "", "qParam": "",
        "view": "", "trn": "0", "page": "", "catid": "", "prodid": "",
        "date": DATE, "classid": "0", "sSU": "",
        "optForwardingLink": "", "isAsync": "false",
    }
    r = s.post(url, data=data, headers={**HEADERS, "Referer": BASE})
    ok = "idsrvauth" in s.cookies
    log.info("Login %s", "OK" if ok else "FAILED")
    return ok

def find_class(s: requests.Session):
    """
    Lekéri az órarendet és megkeresi az adott óra SignupButton URL-jét.
    Visszaadja a classId-t ha megtalálta, None-t ha még nem foglalható.
    """
    data = {
        "pageNum": "1",
        "requiredtxtUserName": "", "requiredtxtPassword": "",
        "optForwardingLink": "", "optRememberMe": "",
        "tabID": "7", "optView": "week", "useClassLogic": "true",
        "filterByClsSch": "", "prevFilterByClsSch": "-1",
        "prevFilterByClsSch2": "-2",
        "txtDate": DATE,
        "optLocation": LOC,
        "optVT": "0", "optInstructor": "0",  # minden edző, majd mi szűrünk
    }
    r = s.post(
        f"{BASE}/classic/mainclass",
        data=data,
        headers={**HEADERS, "Referer": f"{BASE}/classic/mainclass"},
    )
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select(".row")

    for row in rows:
        # Ellenőrizzük az edző nevét és az óra nevét
        text = row.get_text(" ", strip=True)
        if INSTR not in text or CLASS not in text:
            continue

        # Megvan a sor – van-e SignupButton?
        btn = row.select_one("input.SignupButton")
        if not btn:
            log.info("Óra megtalálva, de a foglalás még nem nyílt meg.")
            return None

        # Kinyerjük a classId-t az onclick attribútumból
        onclick = btn.get("onclick", "")
        # onclick = "...classId=11074&classDate=..."
        for part in onclick.split("&"):
            if "classId=" in part:
                class_id = part.split("classId=")[1].split("&")[0].strip("'\"")
                log.info("SignupButton megtalálva! classId=%s", class_id)
                return class_id

    log.info("Az óra nem szerepel az órarenden (dátum: %s).", DATE)
    return None

def get_csrf(s: requests.Session, class_id: str) -> tuple[str, str]:
    """
    Lekéri a res_a.asp oldalt és kinyeri a CSRF tokent + res_deb URL-t.
    """
    url = f"{BASE}/ASP/res_a.asp?tg={TG}&classId={class_id}&classDate={DATE}&clsLoc={LOC}"
    r = s.get(url, headers={**HEADERS, "Referer": f"{BASE}/classic/mainclass"})
    soup = BeautifulSoup(r.text, "html.parser")

    csrf = soup.select_one("input.csrf-token")
    if not csrf:
        log.error("CSRF token nem található a res_a oldalon!")
        return None, None
    csrf_val = csrf["value"]

    # res_deb URL kinyerése a Foglalás gomb onclick-jéből
    btn = soup.select_one("input.actionButton[onclick*='res_deb']")
    if not btn:
        log.error("Foglalás gomb nem található!")
        return csrf_val, None

    onclick = btn.get("onclick", "")
    # submitResForm('res_deb.asp?classID=...', false, false)
    start = onclick.find("'") + 1
    end = onclick.find("'", start)
    res_deb_path = onclick[start:end]

    log.info("CSRF: %s, res_deb: %s", csrf_val, res_deb_path)
    return csrf_val, res_deb_path

def book(s: requests.Session, csrf: str, res_deb_path: str) -> bool:
    """
    Elvégzi a tényleges foglalást a res_deb.asp-n.
    """
    url = f"{BASE}/ASP/{res_deb_path}"
    data = {
        "CSRFToken": csrf,
        "courseID": "", "firstLoad": "false",
        "frmEnrollClientID": "", "courseid": "",
        "frmRtnScreen": "res_a",
        "frmRtnAction": f"res_a.asp?classDate={DATE}&rtnScreen2=cls_list&paid=true",
        "frmUsePmtPlan": "",
        "frmRtnScreen2": "cls_list",
        "lastClientID": "",
        "optReservedFor": "", "optPaidForOther": "", "OptSelf": "",
        "txtResNotes": "",
        "optRecNum": "1", "optRecType": "1",
        "optDay7": "on",
        "txtSDate": DATE, "txtEDate": DATE,
        "rec": "", "numReservations": "1",
    }
    r = s.post(
        url, data=data,
        headers={**HEADERS, "Referer": f"{BASE}/ASP/res_a.asp"},
    )

    # Sikeres foglalás jelei: átirányít vagy tartalmaz megerősítő szöveget
    success = (
        r.status_code == 200
        and ("my_sch" in r.url or "Foglalt" in r.text or "Reserved" in r.text
             or "receipt" in r.url.lower())
    )
    log.info("Foglalás %s (status=%s, url=%s)",
             "SIKERES ✅" if success else "SIKERTELEN ❌",
             r.status_code, r.url)
    return success

def run():
    s = requests.Session()

    # 1. Bejelentkezés
    if not login(s):
        log.error("Bejelentkezés sikertelen, kilépés.")
        sys.exit(1)

    # 2. Figyelés – 30 másodpercenként próbálkozik, max 20 percig
    max_tries = 40
    for attempt in range(1, max_tries + 1):
        log.info("Kísérlet %d/%d – keresem az órát...", attempt, max_tries)
        class_id = find_class(s)

        if class_id:
            # 3. CSRF token lekérése
            csrf, res_deb_path = get_csrf(s, class_id)
            if not csrf or not res_deb_path:
                log.error("Nem sikerült a foglalási adatokat lekérni.")
                sys.exit(1)

            # 4. Foglalás
            if book(s, csrf, res_deb_path):
                log.info("Kész! Az időpont le van foglalva.")
                sys.exit(0)
            else:
                log.error("A foglalás nem sikerült.")
                sys.exit(1)

        if attempt < max_tries:
            log.info("Várakozás 30 másodpercet...")
            time.sleep(30)

    log.error("Időtúllépés – %d kísérlet után sem nyílt meg a foglalás.", max_tries)
    sys.exit(1)

if __name__ == "__main__":
    run()
