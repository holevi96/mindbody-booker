# 🏋️ Mindbody Auto Booker

Automatikus időpontfoglaló a Mindbody Online rendszerhez. Bejelentkezel, beállítod az edzést, éjfélkor lefoglalja helyetted.

---

## Hogyan működik?

```
Bejelentkezel a weboldalon (Supabase Auth)
        ↓
Kitöltöd az edzés adatait + mikor induljon el
        ↓
A backend (Railway) eltárolja az adatbázisban
        ↓
A backend scheduler a beállított időpontban elindítja a Booker scriptet
        ↓
A Booker bejelentkezik a Mindbody-ra és lefoglalja az edzést ✅
        ↓
Ha betelt: automatikusan várólistára iratkozik fel
        ↓
Valós idejű értesítés jelenik meg a böngészőben
```

---

## Architektúra

```
Böngésző (GitHub Pages)
    → Supabase Auth (bejelentkezés)
    → FastAPI backend (Railway)
        → Supabase Postgres (foglalások + titkosított MB credentials)
        → GitHub Actions book.yml (Playwright foglalás)
```

---

## Fájlok

| Fájl | Leírás |
|---|---|
| `index.html` | Webes felület – bejelentkezés, foglalás ütemezése, foglalások listája |
| `booker.py` | Playwright-alapú Mindbody foglalás script |
| `backend/main.py` | FastAPI backend – scheduler, API végpontok, GH Actions trigger |
| `.github/workflows/book.yml` | GitHub Actions job – futtatja a `booker.py`-t |
| `supabase_schema.sql` | Adatbázis séma – egyszeri futtatás a Supabase SQL editorban |
| `requirements.txt` | Python függőségek (Railway) |
| `Procfile` | Railway start parancs |

---

## Beállítás

### 1. Supabase

1. Hozz létre ingyenes projektet: [supabase.com](https://supabase.com)
2. **SQL Editor** → illeszd be a `supabase_schema.sql` tartalmát → **Run**
3. **Authentication → Users** → hozz létre felhasználót minden személynek (email + jelszó)
4. **Database → Publications → supabase_realtime** → add hozzá a `bookings` táblát (valós idejű értesítésekhez)
5. **Settings → API**-ból gyűjtsd össze:
   - Project URL (`https://xxx.supabase.co`)
   - `anon` kulcs (publikus, biztonságos a frontenden)
   - `service_role` kulcs (titkos, csak Railway-be kerül)

### 2. Encryption key generálása

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Tárold biztonságosan – ez titkosítja a Mindbody jelszavakat az adatbázisban.

### 3. Railway

1. Új projekt → **Deploy from GitHub repo** → `main` branch
2. Környezeti változók beállítása:

| Változó | Érték |
|---|---|
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | service_role kulcs |
| `ENCRYPTION_KEY` | a fenti generált kulcs |
| `GITHUB_TOKEN` | PAT `workflow` scope-pal |
| `GITHUB_REPO` | `felhasználónév/mindbody-booker` |

3. Railway automatikusan detektálja a `Procfile`-t és elindítja a szervert.

### 4. GitHub token (MY_PAT secret)

A repóban: **Settings → Secrets and variables → Actions → New repository secret**

| Név | Érték |
|---|---|
| `MY_PAT` | ugyanaz a PAT, mint fent |

### 5. GitHub Pages bekapcsolása

**Settings → Pages → Source: Deploy from a branch → Branch: main / (root) → Save**

Pár perc múlva elérhető: `https://FELHASZNÁLÓNÉV.github.io/mindbody-booker`

---

## Használat

1. Nyisd meg a weboldalt és jelentkezz be
2. Kattints a **⚙️** ikonra → add meg a Mindbody email és jelszó adataidat → **Mentés**
3. Töltsd ki az edzés adatait:
   - **Edző neve** – legördülő listából; ⭐ gombbal kedvencnek jelölheted (mindig a lista tetején lesz)
   - **Edzés dátuma** – naptárból választhatsz
   - **Óra kezdete** – pl. `11:00`; ha az edző ugyanazon a napon több órát tart, ez azonosítja a helyeset
   - **Helyszín** – legördülő listából
4. Állítsd be **mikor induljon el** a foglalás (általában éjfél előtt 2-3 perccel: `23:57`)
5. Kattints **⏰ Foglalás ütemezése**

A foglalás megjelenik a listában `Várakozik` státusszal. A beállított időpontban a backend automatikusan elindítja a foglalást, és valós idejű értesítést kapsz az eredményről.

---

## Státuszok

| Státusz | Leírás |
|---|---|
| Várakozik | Ütemezve, még nem indult el |
| Folyamatban | A Booker script fut |
| Sikeres | Foglalás sikerült ✅ |
| Várólista | Az óra betelt, várólistára kerültél |
| Sikertelen | A foglalás nem sikerült |
| Törölve | Manuálisan törölve |

---

## Fontos tudnivalók

**Időzítés:** érdemes 2-3 perccel a foglalás nyílása előtt ütemezni. A script 30 másodpercenként próbálkozik, amíg meg nem jelenik a foglalás gomb.

**GitHub Actions limit:** az ingyenes GitHub csomag 2000 perc/hónap Actions időt tartalmaz. A Booker kb. 2-5 percet használ foglalásanként – bőven elegendő.

**Biztonság:** a Mindbody jelszó titkosítva (Fernet) van tárolva az adatbázisban. A frontend nem látja a jelszót, csak a backend olvassa ki a booking triggerkor.

---

## Helyszín ID-k (Life1)

| Klub | ID |
|---|---|
| Life1 Corvin Wellness | `2` |
| Life1 Nyugati Fitness | `3` |
| Life1 Allee Fitness | `4` |
| Life1 Etele Fitness | `7` |
| Life1 Fitness Springday | `8` |
| Life1 Fitness Váci35 | `9` |

---

## Hibakeresés

**"Invalid token" / 401** – a Supabase session lejárt, jelentkezz ki és be újra.

**"Configure Mindbody credentials first"** – kattints a ⚙️ ikonra és add meg a Mindbody adataidat.

**"Az óra nem szerepel az órarenden"** – ellenőrizd az edző nevét (ékezetek, szóközök) és az óra kezdési időpontját.

**"Login FAILED"** – ellenőrizd a Mindbody email és jelszó adatokat a ⚙️ beállításokban.

**Foglalás `Sikertelen` maradt** – a GitHub Actions **Actions** fülén megnézheted a részletes logot és letöltheted a hibakori screenshotot.

**Nem jön az értesítés** – ellenőrizd hogy a `bookings` tábla hozzá van-e adva a Supabase Realtime publikációhoz (**Database → Publications → supabase_realtime**).
