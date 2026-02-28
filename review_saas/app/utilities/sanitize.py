# filename: app/utilities/sanitize.py
import bleach

def sanitize_text(value: str) -> str:
    if not value:
        return value
    return bleach.clean(value, strip=True)
