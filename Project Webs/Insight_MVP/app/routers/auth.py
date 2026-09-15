from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User
from ..security import hash_password, verify_password

router = APIRouter()

def templates(request): return request.app.state.templates

@router.get("/register")
def register_page(request: Request):
    return templates(request).TemplateResponse(request, "register.html", {})

@router.post("/register")
def register(request: Request, email: str=Form(...), full_name: str=Form(...), role: str=Form(...), password: str=Form(...), db: Session=Depends(get_db)):
    if role not in {"tenant", "landlord"} or len(password) < 8:
        return templates(request).TemplateResponse(request, "register.html", {"error":"Use tenant/landlord role and a password of at least 8 characters."}, status_code=400)
    if db.scalar(select(User).where(User.email == email.lower().strip())):
        return templates(request).TemplateResponse(request, "register.html", {"error":"Email already registered."}, status_code=400)
    user = User(email=email.lower().strip(), full_name=full_name.strip(), role=role, password_hash=hash_password(password))
    db.add(user); db.commit(); db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)

@router.get("/login")
def login_page(request: Request):
    return templates(request).TemplateResponse(request, "login.html", {})

@router.post("/login")
def login(request: Request, email: str=Form(...), password: str=Form(...), db: Session=Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not verify_password(password, user.password_hash):
        return templates(request).TemplateResponse(request, "login.html", {"error":"Invalid email or password."}, status_code=400)
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)

@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
