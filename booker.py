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


def find_and_click(page) -> bool:
    """
    Lekéri az órarendet, megkeresi az órát és rákattint a SignupButton-ra.
    True-t ad vissza ha kattintott, False-t ha még nem foglalható.
    """
    log.info("Órarend lekérése (dátum: %s)...", DATE)
    page.goto(f"{BASE}/classic/mainclass?fl=true&tabID=7", wait_until="domcontentloaded")

    # Dátum és helyszín beállítása
    page.evaluate(f"""
        document.querySelector('input[name="txtDate"]').value = '{DATE}';
        document.querySelector('select[name="optLocation"]').value = '{LOC}';
        document.querySelector('form[name="search2"]').submit();
    """)

    # Megvárjuk amíg a táblázat betöltődik
    try:
        page.wait_for_selector(
            "#classSchedule-mainTable.classSchedule-mainTable-loaded",
            timeout=15_000
        )
    except PWTimeout:
        log.warning("Táblázat nem töltődött be időre.")

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
            return False

        log.info("SignupButton-ra kattintás...")
        with page.expect_navigation(timeout=15_000, wait_until="domcontentloaded"):
            btn.click()
        return True

    log.info("Az óra nem szerepel az órarenden.")
    return False


def book(page) -> bool:
    """
    A res_a oldalon rákattint a foglalás gombra és megvárja az eredményt.
    """
    log.info("Foglalás gomb keresése...")

    try:
        btn = page.wait_for_selector(
            "input.actionButton[onclick*='res_deb']",
            timeout=10_000
        )
    except PWTimeout:
        log.error("Foglalás gomb nem jelent meg!")
        return False

    log.info("Foglalás gombra kattintás...")
    with page.expect_navigation(timeout=15_000, wait_until="domcontentloaded"):
        btn.click()

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
                clicked = find_and_click(page)

                if clicked:
                    # 3. res_a oldalon vagyunk – kattintunk a foglalás gombra
                    if book(page):
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
