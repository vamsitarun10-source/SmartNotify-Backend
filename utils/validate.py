import re
from fastapi import HTTPException


def validate_email(email: str) -> str:
    email = email.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(email) > 254:
        raise HTTPException(status_code=400, detail="Email too long")
    return email


def validate_password(password: str) -> str:
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="Password too long")
    return password


def validate_string(value: str, field_name: str, min_len: int = 1, max_len: int = 200) -> str:
    value = value.strip()
    if len(value) < min_len:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    if len(value) > max_len:
        raise HTTPException(status_code=400, detail=f"{field_name} too long (max {max_len} chars)")
    return value


def validate_date(date_str: str) -> str:
    if date_str and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")
    return date_str


def validate_time(time_str: str) -> str:
    if time_str and not re.match(r"^\d{2}:\d{2}$", time_str):
        raise HTTPException(status_code=400, detail="Invalid time format (HH:MM)")
    return time_str


def sanitize_text(text: str) -> str:
    """Remove potentially harmful characters from user input."""
    text = re.sub(r"[<>&\"']", "", text)
    return text.strip()
