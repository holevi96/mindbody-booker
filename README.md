# 🏋️ Mindbody Auto Booker

Automatikus időpontfoglaló a Mindbody Online rendszerhez. Beállítod napközben, éjfélkor lefoglalja az edzést helyetted.

---

## Hogyan működik?

```
Te kitöltöd a weboldalt (edző, óra, dátum, időpont)
        ↓
A weboldal elmenti az adatokat a repóba (schedule.json)
        ↓
Elindul a Watcher – figyeli az órát
        ↓
Elérte az időpontot → elindítja a Booker scriptet
        ↓
A Booker bejelentkezik a Mindbody-ra és lefoglalja az edzést ✅
```

---

## Fájlok

| Fájl | Leírás |
|---|---|
| `index.html` | Webes felület – itt ütemezed a foglalást |
| `booker.py` | A tényleges foglalást végző Python script |
| `.github/workflows/watcher.yml` | Figyeli az időpontot, majd elindítja a bookert |
| `.github/workflows/book.yml` | Lefuttatja a `booker.py`-t |
| `schedule.json` | Az ütemezett foglalás adatai (automatikusan jön létre) |

---

## Beállítás (egyszer kell)

### 1. GitHub token létrehozása

1. Menj ide: [github.com/settings/tokens/new](https://github.com/settings/tokens/new)
2. Töltsd ki:
   - **Note:** `mindbody-booker`
   - **Expiration:** No expiration
   - **Scopes:** pipáld be a `workflow` checkboxot
3. Kattints **Generate token** → **azonnal másold ki!**

### 2. MY_PAT secret beállítása

A repóban: **Settings → Secrets and variables → Actions → New repository secret**

| Név | Érték |
|---|---|
| `MY_PAT` | az előbb létrehozott GitHub token |

### 3. GitHub Pages bekapcsolása

A repóban: **Settings → Pages → Source: Deploy from a branch → Branch: main / (root) → Save**

Pár perc múlva elérhető: `https://FELHASZNÁLÓNÉV.github.io/mindbody-booker`

### 4. Weboldal beállítása

Nyisd meg a weboldalt és kattints a **⚙️ Beállítások** gombra:

| Mező | Leírás |
|---|---|
| GitHub token | az 1. lépésben létrehozott token |
| GitHub repó | `felhasználónév/mindbody-booker` |
| Mindbody email | a Mindbody fiókod email címe |
| Mindbody jelszó | a Mindbody fiókod jelszava |
| Studio ID | az edzőterem azonosítója (Life1 Corvin Wellness = `48016`) |

Kattints **Beállítások mentése** – ezután nem kell többé megadni.

---

## Használat

1. Nyisd meg a weboldalt: `https://FELHASZNÁLÓNÉV.github.io/mindbody-booker`
2. Töltsd ki az edzés adatait:
   - **Edző neve** – pontosan ahogy a Mindbody-n szerepel (pl. `Ujvári Cili`)
   - **Óra neve** – pontosan ahogy a Mindbody-n szerepel (pl. `TRX köredzés`)
   - **Edzés dátuma** – `nap/hónap/év` formátumban (pl. `30/03/2026`)
   - **Helyszín ID** – Life1 Corvin Wellness esetén `2`
3. Állítsd be az időpontot – mikor induljon el a foglalás (általában éjfél előtt 2-3 perccel: `23:57`)
4. Kattints **⏰ Foglalás ütemezése**

A rendszer elmenti az adatokat és elindítja a Watchert, ami pontosan a megadott időpontban lefoglalja az edzést.

---

## Fontos tudnivalók

**Dátum formátuma:** mindig `nap/hónap/év` – pl. `30/03/2026` ✅, nem `3/30/2026` ❌

**Időzítés:** a GitHub Actions cron nem garantáltan pontos, ezért érdemes 2-3 perccel a foglalás nyílása előtt ütemezni. A script 30 másodpercenként próbálkozik amíg meg nem jelenik a foglalás gomb.

**Watcher futási idő:** a Watcher GitHub Actions job maximum 6 óráig futhat. Ha ennél többel korábban ütemezed a foglalást mint ahogy megnyílik, a Watcher lejár. Érdemes legfeljebb 5-6 órával korábban elindítani.

**GitHub Actions limit:** az ingyenes GitHub csomag 2000 perc/hónap Actions időt tartalmaz. A Watcher és a Booker együttesen kb. 5-10 percet használ foglalásanként, tehát havonta ~200 foglalást lehetne elvégezni – a gyakorlatban ez bőven elegendő.

**Biztonság:** a Mindbody jelszó soha nem kerül fájlba – csak a GitHub Actions futási környezetében él, titkosítva. A `schedule.json` csak az óra adatait tartalmazza (edző, dátum), jelszót nem.

---

## Helyszín ID-k (Life1)

| Klub | ID |
|---|---|
| Life1 Corvin Wellness | `2` |
| Life1 Allee Fitness | `4` |
| Life1 Nyugati Fitness | `3` |
| Life1 Etele Fitness | `7` |
| Life1 Fitness Springday | `8` |
| Life1 Fitness Váci35 | `9` |

---

## Hibakeresés

**"Watcher indítási hiba (422)"** – a `watcher.yml` régi verzió van a repóban, frissítsd a fájlt.

**"Watcher indítási hiba (403)"** – a GitHub token nem megfelelő. Hozz létre új Classic tokent `workflow` scope-pal és frissítsd a `MY_PAT` secretet.

**"Az óra nem szerepel az órarenden"** – ellenőrizd hogy az edző neve és az óra neve pontosan egyezik-e a Mindbody-n látható névvel (ékezetek, szóközök).

**"Login FAILED"** – ellenőrizd a Mindbody email és jelszó adatokat a Beállításokban.

Ha a foglalás nem sikerül, a GitHub Actions **Actions** fülén megnézheted a részletes logot és letöltheted a hibakori screenshotot.
