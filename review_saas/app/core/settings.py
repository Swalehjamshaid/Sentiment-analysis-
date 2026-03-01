# File: app/core/settings.py
from __future__ import annotations
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ---- App ----
    APP_NAME: str = "ReviewSaaS"
    SECRET_KEY: str = "dev-secret"  # Override via env in production

    # ---- Database ----
    DATABASE_URL: Optional[str] = None
    # Some platforms expose a public DB URL separately (we won't use it directly, but accept it to avoid crashes)
    DATABASE_PUBLIC_URL: Optional[str] = Field(None, alias="database_public_url")

    # ---- Cookies / Auth (session-first; JWT optional) ----
    COOKIE_DOMAIN: Optional[str] = Field(None, alias="cookie_domain")
    COOKIE_SECURE: bool = Field(default=False, alias="cookie_secure")  # true/false string ok with case_sensitive=False
    ACCESS_TOKEN_MIN: Optional[int] = Field(None, alias="access_token_min")  # if you ever use token mins
    JWT_ALG: Optional[str] = Field(None, alias="jwt_alg")
    JWT_SECRET: Optional[str] = Field(None, alias="jwt_secret")
    VERIFY_TOKEN_HOURS: Optional[int] = Field(None, alias="verify_token_hours")
    PASSLIB_MAX_PASSWORD_SIZE: Optional[int] = Field(None, alias="passlib_max_password_size")

    # ---- App base URL (useful for constructing absolute redirects) ----
    APP_BASE_URL: Optional[str] = Field(None, alias="app_base_url")

    # ---- Google / Maps ----
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    # accept legacy env names often used in different codebases
    GOOGLE_PLACES_API_KEY: Optional[str] = Field(None, alias="google_places_api_key")
    GOOGLE_BUSINESS_API_KEY: Optional[str] = Field(None, alias="google_business_api_key")

    # Optional: Service Account file path & scopes (comma-separated)
    GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = None
    GOOGLE_SCOPES: Optional[str] = None  # e.g. "scope1,scope2,scope3"

    # ---- OAuth (Google) ----
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = Field(None, alias="oauth_google_client_id")
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = Field(None, alias="oauth_google_client_secret")
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = Field(None, alias="oauth_google_redirect_uri")

    # ---- Model behavior ----
    # - extra='ignore' → Do NOT crash on unknown env keys
    # - case_sensitive=False → 'smtp_username' and 'SMTP_USERNAME' both match if field exists
    # - env_prefix='' → no forced prefix
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        env_prefix="",
    )

    # ---- SMTP (to avoid extra_forbidden if present in env) ----
    SMTP_USERNAME: Optional[str] = Field(None, alias="smtp_username")
    SMTP_PASSWORD: Optional[str] = Field(None, alias="smtp_password")

    # You can add more Optional[...] fields here as your environment grows,
    # or keep relying on extra="ignore" to safely ignore unknown keys.

settings = Settings()
