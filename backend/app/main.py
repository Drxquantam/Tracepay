"""TracePay API entry point. SIMULATION ONLY: fake money, fake banks, mock UPI switch."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, health

app = FastAPI(
    title="TracePay API (simulation only)",
    description="Simulated UPI-style payments. No real money, banks or NPCI integration.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
