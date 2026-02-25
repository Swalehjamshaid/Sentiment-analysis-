# FILE: app/context.py
from typing import Dict, Any
from .db import get_db
from .models import Company
from .services.rbac import get_current_user

def common_context(request) -> Dict[str, Any]:
    """
    Centralized context for all templates to ensure base variables 
    (user, companies, CSRF) are always available.
    """
    user = None
    try:
        user = get_current_user(request)
    except Exception:
        user = None

    db = next(get_db())
    try:
        companies_list = db.query(Company).order_by(Company.name.asc()).all()
    except Exception:
        companies_list = []
    finally:
        db.close()

    flash_error = request.session.pop("flash_error", None)

    return {
        "request": request,
        "current_user": user,
        "is_authenticated": user is not None,
        "companies": companies_list,
        "apiBase": "",
        "flash_error": flash_error,
    }
