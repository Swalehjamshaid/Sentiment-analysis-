# review_saas/app/services/rbac.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Example OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dummy user roles storage for example
fake_users_db = {
    "admin_token": {"username": "admin", "roles": ["admin", "user"]},
    "user_token": {"username": "user", "roles": ["user"]},
}

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Get current user from token.
    """
    user = fake_users_db.get(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return user

def require_roles(required_roles: list):
    """
    Dependency to require specific roles.
    """
    def role_checker(user: dict = Depends(get_current_user)):
        user_roles = user.get("roles", [])
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user
    return role_checker
