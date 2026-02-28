# filename: app/models/base.py
from sqlalchemy.orm import declarative_base

# Requirement #124: Centralized Base for all SQLAlchemy models
# This object keeps track of all tables defined in your models.py
Base = declarative_base()
