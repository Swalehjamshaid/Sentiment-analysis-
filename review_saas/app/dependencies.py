# File: app/dependencies.py
from typing import Dict, Any, Optional
from fastapi import Request

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get user from session. Returns None if not logged in.
    Moved to this separate file to break the circular import loop 
    between main.py and the route files.
    """
    user = request.session.get("user")
    return user if user else None
