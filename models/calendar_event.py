from typing import Optional
from pydantic import BaseModel, Field


class CalendarEventCreate(BaseModel):
    title: str = Field(..., min_length=1)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: str = "personal"
    notes: str = ""


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: Optional[str] = None
    notes: Optional[str] = None


class CalendarEventOut(BaseModel):
    id: str
    owner_id: str
    title: str
    date: str
    category: str = "personal"
    notes: str = ""
    created_at: str = ""
