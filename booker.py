"""
Mindbody automatikus időpontfoglaló – Playwright alapú
"""
import os, re, sys, time, logging
from datetime import datetime, date as Date
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

BASE       = "https://clients.mindbodyonline.com"
STUDIO_ID  = os.environ["MB_STUDIO_ID"]   # 48016
EMAIL      = os.environ["MB_EMAIL"]
PASSWD     = os.environ["MB_PASSWORD"]
INSTR      = os.environ["MB_INSTRUCTOR"]  # pl. "Ujvári Cili"
CLASS      = os.environ.get("MB_CLASS", "")
DATE       = os.environ["MB_CLASS_DATE"]  # pl. "3/25/2026"
LOC        = os.environ.get("MB_LOCATION", "2")
TG         = os.environ.get("MB_TG", "23")
MAX_TRIES  = int(os.environ.get("MB_MAX_TRIES", "40"))
RETRY_SEC  = int(os.environ.get("MB_RETRY_SEC", "30"))


_HU_EN_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'már': 3, 'apr': 4, 'ápr': 4,
    'may': 5, 'máj': 5, 'jun': 6, 'jún': 6, 'jul': 7, 'júl': 7,
    'aug': 8, 'sep': 9, 'sze': 9, 'oct': 10, 'okt': 10,
    'nov': 11, 'dec': 12,
}

def _parse_header_date(text: str) -> Date | None:
    """Extract date from a header like 'Szerda/Wednesday 01 Április/April 2026'."""
    m = re.search(r'(\d{1,2})\s+\w+/(\w+)\.?\s+(\d{4})', text)
    if not m:
        return None
    day, month_key, year = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
    month = _HU_EN_MONTHS.get(month_key)
    if not month:
        return None
    try:
        return Date(year, month, day)
    except ValueError:
        return None


def _parse_target_date() -> Date:
    """Parse MB_CLASS_DATE env var (DD/MM/YYYY)."""
    return datetime.strptime(DATE, "%d/%m/%Y").date()


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

    A heti nézet több azonos nevű órát is tartalmazhat (pl. ugyanaz az edző
    hétfőn és szerdán is). A dátum egyezést kétféleképpen ellenőrzi:
      1. A SignupButton onclick attribútumából kiolvasott classDate (legmegbízhatóbb)
      2. Az előző .header div szövegéből kinyert dátum (fallback, ha nincs gomb)
    """
    target = _parse_target_date()
    log.info("Órarend lekérése (dátum: %s → %s)...", DATE, target)
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

    container = page.query_selector("#classSchedule-mainTable")
    if not container:
        log.warning("Tábla konténer nem található.")
        return False

    children = container.query_selector_all(":scope > div")
    log.info("%d elem a táblában.", len(children))

    current_date: Date | None = None

    for child in children:
        cls = child.get_attribute("class") or ""

        if "header" in cls:
            current_date = _parse_header_date(child.inner_text())
            if current_date:
                log.info("Fejléc dátum: %s", current_date)
            continue

        if "row" not in cls:
            continue

        # Ha van SignupButton, a classDate az onclick-ből a legmegbízhatóbb dátum
        btn = child.query_selector("input.SignupButton")
        if btn:
            onclick = btn.get_attribute("onclick") or ""
            m = re.search(r'classDate=(\d+/\d+/\d+)', onclick)
            if m:
                try:
                    current_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                except ValueError:
                    pass

        if current_date != target:
            continue

        text = child.inner_text()
        if INSTR not in text:
            continue
        if CLASS and CLASS not in text:
            continue

        log.info("Óra megtalálva (dátum: %s): %s", current_date, text[:80].replace("\n", " "))

        if not btn:
            log.info("Foglalás még nem nyílt meg.")
            return False

        log.info("SignupButton-ra kattintás...")
        with page.expect_navigation(timeout=15_000, wait_until="domcontentloaded"):
            btn.click()
        return True

    log.info("Az óra nem szerepel az órarenden (keresett dátum: %s).", target)
    return False


def book(page) -> bool:
    """
    A res_a oldalon rákattint a foglalás gombra és megvárja az eredményt.
    Ha az óra betelt, megpróbál várólistára kerülni.
    """
    log.info("Foglalás gomb keresése...")

    # Wait for either the regular booking button or the waitlist button
    try:
        page.wait_for_selector(
            "input.actionButton[onclick*='res_deb'], input[name='AddWLButton']",
            timeout=10_000
        )
    except PWTimeout:
        page.screenshot(path="debug_timeout.png")
        log.error("Foglalás gomb nem jelent meg! Screenshot: debug_timeout.png")
        return False

    # Megvizsgáljuk hogy betelt-e az óra (várólista eset)
    waitlist_btn = page.query_selector("input[name='AddWLButton']")
    if waitlist_btn:
        return _join_waitlist(page, waitlist_btn)

    btn = page.query_selector("input.actionButton[onclick*='res_deb']")

    log.info("Foglalás gombra kattintás...")
    with page.expect_navigation(timeout=15_000, wait_until="domcontentloaded"):
        btn.click()

    return _check_booking_success(page)


def _join_waitlist(page, btn) -> bool:
    """Várólistára való feliratkozás kezelése."""
    log.info("Az óra betelt – várólistára feliratkozás...")
    try:
        with page.expect_navigation(timeout=15_000, wait_until="domcontentloaded"):
            btn.click()
    except PWTimeout:
        # addToWaitList() esetleg nem navigál, ellenőrizzük az oldalt
        pass

    url = page.url
    content = page.content()
    success = (
        "waitlist" in url.lower()
        or "WaitList" in content
        or "várólista" in content.lower()
        or "wait list" in content.lower()
        or "waitlist" in content.lower()
    )
    log.info(
        "Várólistára feliratkozás %s (url=%s)",
        "SIKERES ✅" if success else "SIKERTELEN ❌", url
    )
    if not success:
        log.info("Oldal tartalom (első 500 kar): %s", content[:500])
    return success


def _check_booking_success(page) -> bool:
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
