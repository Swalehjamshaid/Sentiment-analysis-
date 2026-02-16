# review_saas/app/deps.py
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from .db import get_db
from .models import User
from .utils.security import ALGORITHM
from .config import SECRET_KEY

async def get_current_user(req: Request, db: Session = Depends(get_db)) -> User:
    token = req.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        user = db.query(User).get(int(sub))
        if not user or user.status == "suspended":
            raise HTTPException(status_code=401, detail="Invalid session")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
