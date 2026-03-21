"""
Mindbody automatikus időpontfoglaló – Playwright alapú
"""
import os, sys, time, logging
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

BASE       = "https://clients.mindbodyonline.com"
STUDIO_ID  = os.environ["MB_STUDIO_ID"]   # 48016
EMAIL      = os.environ["MB_EMAIL"]
PASSWD     = os.environ["MB_PASSWORD"]
INSTR      = os.environ["MB_INSTRUCTOR"]  # pl. "Ujvári Cili"
CLASS      = os.environ["MB_CLASS"]       # pl. "TRX köredzés"
DATE       = os.environ["MB_CLASS_DATE"]  # pl. "3/25/2026"
LOC        = os.environ.get("MB_LOCATION", "2")
TG         = os.environ.get("MB_TG", "23")
MAX_TRIES  = int(os.environ.get("MB_MAX_TRIES", "40"))
RETRY_SEC  = int(os.environ.get("MB_RETRY_SEC", "30"))


def login(page) -> bool:
    log.info("Bejelentkezés...")
    page.goto(
        f"{BASE}/ASP/su1.asp?studioid={STUDIO_ID}",
        wait_until="domcontentloaded"
    )
    # Email + jelszó mezők kitöltése
    page.fill("input#su1UserName", EMAIL)
    page.fill("input#su1Password", PASSWD)
    page.click("input#btnSu1Login")

    try:
        # Sikeres login után az oldal átirányít
        page.wait_for_url(f"**/{STUDIO_ID}**", timeout=15_000)
    except PWTimeout:
        pass

    # Ellenőrzés: be vagyunk-e lépve
    ok = "idsrvauth" in {c["name"] for c in page.context.cookies()}
    log.info("Login %s", "OK ✅" if ok else "FAILED ❌")
    return ok


def find_class(page) -> str | None:
    """
    Lekéri az órarendet és megkeresi az adott óra SignupButton-ját.
    Visszaadja a classId-t ha megtalálta, None-t ha még nem foglalható.
    """
    log.info("Órarend lekérése (dátum: %s)...", DATE)
    page.goto(f"{BASE}/classic/mainclass?fl=true&tabID=7", wait_until="domcontentloaded")

    # Dátum beállítása és szűrés
    page.evaluate(f"""
        document.querySelector('input[name="txtDate"]').value = '{DATE}';
        document.querySelector('select[name="optLocation"]').value = '{LOC}';
        document.querySelector('form[name="search2"]').submit();
    """)
    # Megvárjuk amíg a táblázat betöltődik (AJAX)
    try:
        page.wait_for_selector(
            "#classSchedule-mainTable.classSchedule-mainTable-loaded",
            timeout=15_000
        )
    except PWTimeout:
        log.warning("Táblázat nem töltődött be időre.")

    # Összes sor a táblázatban
    rows = page.query_selector_all(".row")
    log.info("%d sor az órarendben.", len(rows))

    for row in rows:
        text = row.inner_text()
        if INSTR not in text or CLASS not in text:
            continue

        log.info("Óra megtalálva: %s", text[:80].replace("\n", " "))

        btn = row.query_selector("input.SignupButton")
        if not btn:
            log.info("Foglalás még nem nyílt meg.")
            return None

        onclick = btn.get_attribute("onclick") or ""
        for part in onclick.split("&"):
            if "classId=" in part:
                class_id = part.split("classId=")[1].split("'")[0].split("&")[0]
                log.info("SignupButton megtalálva! classId=%s", class_id)
                return class_id

    log.info("Az óra nem szerepel az órarenden.")
    return None


def get_csrf_and_book_url(page, class_id: str) -> tuple[str, str] | tuple[None, None]:
    """
    Megnyitja a res_a.asp oldalt és kinyeri a CSRF tokent + res_deb URL-t.
    """
    url = f"{BASE}/ASP/res_a.asp?tg={TG}&classId={class_id}&classDate={DATE}&clsLoc={LOC}"
    log.info("res_a.asp megnyitása: %s", url)
    page.goto(url, wait_until="domcontentloaded")

    csrf = page.query_selector("input.csrf-token")
    if not csrf:
        log.error("CSRF token nem található!")
        return None, None
    csrf_val = csrf.get_attribute("value")

    btn = page.query_selector("input.actionButton[onclick*='res_deb']")
    if not btn:
        log.error("Foglalás gomb nem található!")
        return csrf_val, None

    onclick = btn.get_attribute("onclick") or ""
    # submitResForm('res_deb.asp?classID=...', false, false)
    start = onclick.find("'") + 1
    end   = onclick.find("'", start)
    res_deb_path = onclick[start:end]

    log.info("CSRF: %s", csrf_val)
    log.info("res_deb path: %s", res_deb_path)
    return csrf_val, res_deb_path


def book(page, csrf: str, res_deb_path: str) -> bool:
    """
    Elvégzi a tényleges foglalást a frmRecRes form elküldésével.
    """
    log.info("Foglalás elküldése...")

    # A res_a oldalon vagyunk, elküldjük a formot JS-en keresztül
    # pontosan úgy ahogy a gomb onclick-je tenné
    with page.expect_navigation(timeout=15_000, wait_until="domcontentloaded"):
        page.evaluate(f"""
            document.querySelector('input[name="CSRFToken"]').value = '{csrf}';
            document.frmRecRes.action = '{res_deb_path}';
            document.frmRecRes.submit();
        """)

    url = page.url
    content = page.content()
    success = (
        "my_sch" in url
        or "receipt" in url.lower()
        or "Foglalt" in content
        or "Reserved" in content
        or "confirmed" in content.lower()
    )
    log.info(
        "Foglalás %s (url=%s)",
        "SIKERES ✅" if success else "SIKERTELEN ❌", url
    )
    if not success:
        log.info("Oldal tartalom (első 500 kar): %s", content[:500])
    return success


def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            locale="hu-HU",
        )
        page = ctx.new_page()

        try:
            # 1. Bejelentkezés
            if not login(page):
                log.error("Bejelentkezés sikertelen.")
                sys.exit(1)

            # 2. Figyelés – RETRY_SEC másodpercenként, max MAX_TRIES-szor
            for attempt in range(1, MAX_TRIES + 1):
                log.info("── Kísérlet %d/%d ──", attempt, MAX_TRIES)
                class_id = find_class(page)

                if class_id:
                    # 3. CSRF + res_deb URL lekérése
                    csrf, res_deb_path = get_csrf_and_book_url(page, class_id)
                    if not csrf or not res_deb_path:
                        log.error("Foglalási adatok lekérése sikertelen.")
                        sys.exit(1)

                    # 4. Foglalás
                    if book(page, csrf, res_deb_path):
                        log.info("Kész! Az időpont le van foglalva. 🎉")
                        sys.exit(0)
                    else:
                        log.error("A foglalás nem sikerült.")
                        sys.exit(1)

                if attempt < MAX_TRIES:
                    log.info("Várakozás %d másodpercet...", RETRY_SEC)
                    time.sleep(RETRY_SEC)

            log.error("Időtúllépés – %d kísérlet után sem nyílt meg.", MAX_TRIES)
            sys.exit(1)

        except Exception as e:
            log.exception("Váratlan hiba: %s", e)
            # Screenshot mentés hibakereséshez
            try:
                page.screenshot(path="error.png")
                log.info("Screenshot mentve: error.png")
            except Exception:
                pass
            sys.exit(1)

        finally:
            browser.close()


if __name__ == "__main__":
    run()
