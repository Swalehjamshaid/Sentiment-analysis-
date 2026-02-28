# File: review_saas/app/models/base.py
from sqlalchemy.orm import declarative_base
# Fixed import path:
from app.core.settings import settings

# Requirement #124: Centralized Base for all SQLAlchemy models
Base = declarative_base()
