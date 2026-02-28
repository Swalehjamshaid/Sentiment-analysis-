# filename: app/utilities/validators.py
import re
from email_validator import validate_email, EmailNotValidError
from .sanitize import sanitize_text

EMAIL_REGEX = re.compile(r"^.+@.+\..+$")

def is_valid_email(value: str) -> bool:
    try:
        validate_email(value)
        return True
    except EmailNotValidError:
        return False

def sanitize_input(value: str) -> str:
    return sanitize_text(value)
