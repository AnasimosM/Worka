from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from .models import User

def current_user(request: Request, db: Session):
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.get(User, uid)

def require_user(request: Request, db: Session):
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user
