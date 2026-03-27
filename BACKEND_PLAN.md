# Backend Plan – Mindbody Booker

## Status: Implementation complete, not yet deployed

The backend code is fully written on this branch (`feature/backend`).
Deployment is pending (Supabase + Railway setup required).

---

## Architecture

```
User browser (GitHub Pages)
    → Supabase Auth (login/logout)
    → FastAPI backend (Railway)
        → Supabase Postgres (bookings + encrypted MB credentials)
        → GitHub Actions book.yml (Playwright booking — unchanged)
```

**Why this design:**
- Small user group (~5 people), each with their own Mindbody account
- Shared GitHub service token on the backend (not per-user)
- Keeps GitHub Actions for Playwright (free, already working)
- Replaces `watcher.yml` + `schedule.json` with a proper scheduler + DB
  → multiple users can have simultaneous pending bookings

---

## Files added on this branch

| File | Purpose |
|---|---|
| `backend/main.py` | FastAPI app — all routes, scheduler, GH Actions trigger |
| `requirements.txt` | Python deps for Railway |
| `Procfile` | Railway start command |
| `supabase_schema.sql` | Run this in Supabase SQL editor once |
| `index.html` | Rewritten as login-protected SPA |

**Removed:**
- `config.json` — had plaintext Mindbody credentials (security risk)
- `.github/workflows/watcher.yml` — replaced by backend scheduler

---

## Database schema (Supabase)

```sql
user_credentials (id, mb_email, mb_password_encrypted, studio_id)
bookings         (id, user_id, instructor, class_date, location,
                  run_at, status, gh_run_id, error_message, created_at)
```

Booking statuses: `pending → running → success | failed | cancelled`

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/users/me` | Get current user profile + MB email |
| PUT | `/users/me/credentials` | Save/update MB email + password (encrypted) |
| GET | `/bookings` | List user's bookings (last 20) |
| POST | `/bookings` | Create new booking |
| DELETE | `/bookings/{id}` | Cancel pending booking |

---

## Deployment steps (when ready)

### 1. Supabase
- Create free project at supabase.com
- Run `supabase_schema.sql` in the SQL editor
- Create user accounts manually via **Authentication → Users** (invite-only)
- Collect: `Project URL`, `anon key`, `service_role key`, `JWT secret`

### 2. Generate encryption key
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Store this as `ENCRYPTION_KEY` — never commit it.

### 3. Railway
- New project → connect GitHub repo → set root to `/`
- Set environment variables:
  ```
  SUPABASE_URL=https://xxx.supabase.co
  SUPABASE_SERVICE_KEY=<service_role key>
  SUPABASE_JWT_SECRET=<JWT secret>
  ENCRYPTION_KEY=<generated above>
  GITHUB_TOKEN=<PAT with workflow scope>
  GITHUB_REPO=holevi96/mindbody-booker
  ```
- Railway auto-detects `Procfile`: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

### 4. Update index.html
Fill in the three constants in the config script block:
```js
const SUPABASE_URL  = 'https://xxx.supabase.co';
const SUPABASE_ANON = 'eyJ...';   // anon public key (safe to expose)
const API_URL       = 'https://xxx.railway.app';
```
Commit and push → GitHub Pages serves the updated frontend.

### 5. Add users
In Supabase dashboard → Authentication → Users → Invite user (or create manually).
Each user then sets their Mindbody credentials via the ⚙️ settings panel in the app.

---

## How a booking flows end-to-end

```
1. User logs in (Supabase Auth)
2. User fills form → clicks "⏰ Foglalás ütemezése"
3. POST /bookings → stored in DB with status=pending
4. Backend scheduler (every 30s) finds bookings where run_at <= now
5. Triggers book.yml via GitHub API (passes MB credentials + booking params)
6. Scheduler polls GH Actions run status (every 60s)
7. Updates booking status → user sees result in the bookings list
```

---

## Open items / future improvements

- [ ] Email/push notification when a booking succeeds or fails
- [ ] Allow users to change their own password (Supabase supports this)
- [ ] Booking status auto-refresh in the UI (currently requires page reload)
- [ ] Rate limiting on the API endpoints
- [ ] `CORS allow_origins` should be restricted to the GitHub Pages domain in production
