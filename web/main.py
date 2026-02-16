from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from web.routers import auth, schedule, api

import os

app = FastAPI(title="Sport Schedule Web")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-me-in-prod"),
)

app.mount("/static", StaticFiles(directory="web/static"), name="static")

app.include_router(auth.router)
app.include_router(schedule.router)
app.include_router(api.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
