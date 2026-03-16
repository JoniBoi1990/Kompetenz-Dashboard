from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from routers import auth, classes, competencies, records, tests, bookings, admin
from db.session import engine
from models.models import Base
from config import settings

app = FastAPI(title="Kompetenz-Dashboard API", version="1.0.0", root_path="/api")

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, same_site="lax", https_only=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"https://{settings.DOMAIN}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(classes.router, prefix="/classes", tags=["classes"])
app.include_router(competencies.router, prefix="/competencies", tags=["competencies"])
app.include_router(records.router, prefix="/records", tags=["records"])
app.include_router(tests.router, prefix="/tests", tags=["tests"])
app.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/health")
async def health():
    return {"status": "ok"}
