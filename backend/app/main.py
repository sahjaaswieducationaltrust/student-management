import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import close_mongo_connection, connect_to_mongo, get_db
from .routers import (
    attendance,
    auth,
    classrooms,
    dashboard,
    fees,
    staff,
    students,
    teachers,
)
from .security import hash_password
from .utils import now_utc

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")
log = logging.getLogger("preschool")


async def bootstrap_admin() -> None:
    db = get_db()
    if await db.users.count_documents({}) > 0:
        return
    await db.users.insert_one(
        {
            "name": settings.admin_name,
            "email": settings.admin_email.lower(),
            "role": "admin",
            "phone": None,
            "is_active": True,
            "password_hash": hash_password(settings.admin_password),
            "created_at": now_utc(),
        }
    )
    log.info("Created the first admin account: %s", settings.admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    log.info("Connected to MongoDB database %r", settings.mongodb_db)
    await bootstrap_admin()
    yield
    await close_mongo_connection()


app = FastAPI(
    title=f"{settings.school_name} — Management API",
    description=(
        "Preschool management: children, teachers, classes, fee plans, "
        "receipts and attendance."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(auth.users_router)
app.include_router(dashboard.router)
app.include_router(classrooms.router)
app.include_router(students.router)
app.include_router(teachers.router)
app.include_router(staff.router)
app.include_router(fees.router)
app.include_router(attendance.router)


@app.get("/api/health", tags=["health"])
async def health():
    db = get_db()
    await db.client.admin.command("ping")
    return {"status": "ok", "database": settings.mongodb_db, "time": now_utc()}


# --------------------------------------------------------------------------- #
# Serve the built React app (production only)
#
# The deploy pipeline copies frontend/dist into backend/static. When that folder
# exists the API also serves the UI, so the whole thing runs as ONE Azure App
# Service on one origin — no CORS, no second resource to pay for.
# In local development the folder is absent and Vite serves the UI instead.
# --------------------------------------------------------------------------- #
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
API_PREFIXES = ("api/", "docs", "redoc", "openapi.json")

if STATIC_DIR.is_dir():
    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve a real file when it exists, otherwise the SPA entry point.

        Unknown /api paths must still 404 as JSON rather than silently
        returning index.html, which would make API typos very confusing.
        """
        if full_path.startswith(API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")

        if full_path:
            candidate = (STATIC_DIR / full_path).resolve()
            # Guard against `../` traversal escaping the static folder.
            if candidate.is_file() and candidate.is_relative_to(STATIC_DIR):
                return FileResponse(candidate)

        return FileResponse(STATIC_DIR / "index.html")

    log.info("Serving the built frontend from %s", STATIC_DIR)
else:
    log.info("No static build found — API only (run the Vite dev server for the UI)")
