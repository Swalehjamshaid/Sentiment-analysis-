# filename: review_saas/app/routes/auth.py
import logging
logger = logging.getLogger("auth")

# ... keep your existing code ...

# This function is used by main.py /login POST
async def login_post(request: Request, email: str, password: str, db: Session):
    original_email = email
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.info("LOGIN FAIL: user not found email='%s' (original='%s')", email, original_email)
        return None

    hashed = getattr(user, "password_hash", None)
    input_hash = _hash(password)

    if hashed:
        if hashed == input_hash:
            logger.info("LOGIN OK: user_id=%s email=%s", user.id, user.email)
            return user
        else:
            logger.info("LOGIN FAIL: hash mismatch user_id=%s email=%s", user.id, user.email)
            return None

    # Fallback: plain password (legacy)
    if getattr(user, "password", None) and user.password == password:
        logger.info("LOGIN OK (legacy plain): user_id=%s email=%s", user.id, user.email)
        return user

    logger.info("LOGIN FAIL: no matching credential path user_id=%s email=%s", user.id, user.email if user else email)
    return None
