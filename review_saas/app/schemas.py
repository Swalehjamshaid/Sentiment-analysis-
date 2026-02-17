from pydantic import BaseModel, EmailStr, Field
    from typing import Optional

    class RegisterIn(BaseModel):
        full_name: str = Field(..., max_length=100)
        email: EmailStr
        password: str = Field(..., min_length=8)

    class LoginIn(BaseModel):
        email: EmailStr
        password: str

    class CompanyIn(BaseModel):
        name: Optional[str] = None
        place_id: Optional[str] = None
        maps_link: Optional[str] = None
        city: Optional[str] = None