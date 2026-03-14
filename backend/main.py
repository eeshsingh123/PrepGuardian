from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_databases, close_databases
from app.routes import agent
from app.routes import users
from app.routes import conversations
from app.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing PrepGuardian Backend")
    await init_databases()
    yield
    await close_databases()
    logger.info("Shutting down PrepGuardian Backend")

app = FastAPI(
    title="PrepGuardian API",
    description="Backend API for the Live PrepGuardian AI Agent",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router)
app.include_router(users.router)
app.include_router(conversations.router)


@app.get("/")
async def root():
    return {"message": "Welcome to PrepGuardian API", "status": "online"}
