"""Mindbody Booker – FastAPI backend"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from supabase import Client, create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_JWT_SECRET  = os.environ["SUPABASE_JWT_SECRET"]
ENCRYPTION_KEY       = os.environ["ENCRYPTION_KEY"]   # generate: Fernet.generate_key()
GITHUB_TOKEN         = os.environ["GITHUB_TOKEN"]
GITHUB_REPO          = os.environ["GITHUB_REPO"]       # e.g. "holevi96/mindbody-booker"

# ── Clients ────────────────────────────────────────────────────────────────────
db: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

# ── Crypto ─────────────────────────────────────────────────────────────────────
def encrypt(s: str) -> str:
    return fernet.encrypt(s.encode()).decode()

def decrypt(s: str) -> str:
    return fernet.decrypt(s.encode()).decode()

# ── Auth ───────────────────────────────────────────────────────────────────────
bearer = HTTPBearer()

async def get_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        return jwt.decode(
            creds.credentials,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

# ── GitHub Actions ─────────────────────────────────────────────────────────────
GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

async def trigger_book(booking: dict, creds: dict) -> int | None:
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/book.yml/dispatches",
            headers=GH_HEADERS,
            json={
                "ref": "main",
                "inputs": {
                    "instructor":   booking["instructor"],
                    "class_date":   booking["class_date"],
                    "class_time":   booking.get("class_time", ""),
                    "location":     booking["location"],
                    "mb_email":     creds["mb_email"],
                    "mb_password":  decrypt(creds["mb_password_encrypted"]),
                    "mb_studio_id": creds.get("studio_id") or "48016",
                },
            },
        )
        r.raise_for_status()

    await asyncio.sleep(4)  # let GitHub register the run

    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/book.yml/runs",
            headers=GH_HEADERS,
            params={"per_page": 1, "event": "workflow_dispatch"},
        )
        runs = r.json().get("workflow_runs", [])
        return runs[0]["id"] if runs else None

async def get_run_status(run_id: int) -> str:
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs/{run_id}",
            headers=GH_HEADERS,
        )
        d = r.json()
    if d.get("status") == "completed":
        return "success" if d.get("conclusion") == "success" else "failed"
    return "running"

# ── Scheduler ──────────────────────────────────────────────────────────────────
async def _trigger_due():
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = await asyncio.to_thread(
            lambda: db.table("bookings")
                .select("*")
                .eq("status", "pending")
                .lte("run_at", now)
                .execute()
        )
    except Exception as e:
        log.error("Scheduler: DB query failed: %s", e)
        return

    for b in rows.data:
        bid = b["id"]
        try:
            creds_r = await asyncio.to_thread(
                lambda: db.table("user_credentials")
                    .select("mb_email, mb_password_encrypted, studio_id")
                    .eq("id", b["user_id"])
                    .execute()
            )
            if not creds_r.data:
                log.error("Booking %s: no credentials found for user %s", bid, b["user_id"])
                continue
            run_id = await trigger_book(b, creds_r.data[0])
            await asyncio.to_thread(
                lambda: db.table("bookings")
                    .update({"status": "running", "gh_run_id": run_id})
                    .eq("id", bid)
                    .execute()
            )
            log.info("Booking %s triggered → GH run %s", bid, run_id)
        except Exception as e:
            log.error("Booking %s failed to trigger: %s", bid, e)
            err = str(e)
            await asyncio.to_thread(
                lambda: db.table("bookings")
                    .update({"status": "failed", "error_message": err})
                    .eq("id", bid)
                    .execute()
            )

async def _poll_running():
    try:
        rows = await asyncio.to_thread(
            lambda: db.table("bookings")
                .select("id, gh_run_id")
                .eq("status", "running")
                .not_.is_("gh_run_id", "null")
                .execute()
        )
    except Exception as e:
        log.error("Scheduler: poll query failed: %s", e)
        return

    for b in rows.data:
        bid, run_id = b["id"], b["gh_run_id"]
        try:
            s = await get_run_status(run_id)
            if s in ("success", "failed"):
                await asyncio.to_thread(
                    lambda: db.table("bookings").update({"status": s}).eq("id", bid).execute()
                )
                log.info("Booking %s → %s", bid, s)
        except Exception as e:
            log.error("Poll failed for booking %s: %s", bid, e)

# ── App ────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_trigger_due, "interval", seconds=30, id="trigger")
    scheduler.add_job(_poll_running, "interval", seconds=60, id="poll")
    scheduler.start()
    log.info("Scheduler started")
    yield
    scheduler.shutdown()

app = FastAPI(title="Mindbody Booker API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ─────────────────────────────────────────────────────────────────────
class CredentialsIn(BaseModel):
    mb_email: str
    mb_password: str
    studio_id: str = "48016"

class BookingIn(BaseModel):
    instructor: str
    class_date: str        # DD/MM/YYYY
    class_time: str = ""   # HH:MM, optional — disambiguates same-instructor same-day rows
    location: str
    run_at: str            # ISO 8601

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/users/me")
async def me(u=Depends(get_user)):
    r = await asyncio.to_thread(
        lambda: db.table("user_credentials")
            .select("mb_email, studio_id")
            .eq("id", u["sub"])
            .execute()
    )
    return {"email": u.get("email"), **(r.data[0] if r.data else {})}

@app.put("/users/me/credentials")
async def update_credentials(body: CredentialsIn, u=Depends(get_user)):
    await asyncio.to_thread(
        lambda: db.table("user_credentials").upsert({
            "id": u["sub"],
            "mb_email": body.mb_email,
            "mb_password_encrypted": encrypt(body.mb_password),
            "studio_id": body.studio_id,
        }).execute()
    )
    return {"ok": True}

@app.get("/bookings")
async def list_bookings(u=Depends(get_user)):
    r = await asyncio.to_thread(
        lambda: db.table("bookings")
            .select("*")
            .eq("user_id", u["sub"])
            .order("created_at", desc=True)
            .limit(20)
            .execute()
    )
    return r.data

@app.post("/bookings", status_code=201)
async def create_booking(body: BookingIn, u=Depends(get_user)):
    creds = await asyncio.to_thread(
        lambda: db.table("user_credentials")
            .select("mb_email")
            .eq("id", u["sub"])
            .execute()
    )
    if not creds.data or not creds.data[0].get("mb_email"):
        raise HTTPException(400, "Configure Mindbody credentials first")
    r = await asyncio.to_thread(
        lambda: db.table("bookings").insert({
            "user_id":    u["sub"],
            "instructor": body.instructor,
            "class_date": body.class_date,
            "class_time": body.class_time,
            "location":   body.location,
            "run_at":     body.run_at,
            "status":     "pending",
        }).execute()
    )
    return r.data[0]

@app.delete("/bookings/{booking_id}")
async def cancel_booking(booking_id: str, u=Depends(get_user)):
    r = await asyncio.to_thread(
        lambda: db.table("bookings")
            .select("status, user_id")
            .eq("id", booking_id)
            .execute()
    )
    if not r.data:
        raise HTTPException(404, "Not found")
    b = r.data[0]
    if b["user_id"] != u["sub"]:
        raise HTTPException(403, "Forbidden")
    if b["status"] != "pending":
        raise HTTPException(400, "Can only cancel pending bookings")
    await asyncio.to_thread(
        lambda: db.table("bookings")
            .update({"status": "cancelled"})
            .eq("id", booking_id)
            .execute()
    )
    return {"ok": True}
