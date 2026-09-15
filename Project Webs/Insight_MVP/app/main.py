from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
from .config import settings
from .db import Base, engine
from .routers import auth, core

BASE = Path(__file__).resolve().parent
settings.upload_path.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)
app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")
app.state.templates = Jinja2Templates(directory=BASE/"templates")
app.include_router(auth.router)
app.include_router(core.router)
