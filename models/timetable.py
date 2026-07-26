from typing import Optional
from pydantic import BaseModel, Field


class TimetableEntryCreate(BaseModel):
    title: str = Field(..., min_length=1)
    subject: str = ""
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday 6=Sunday")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    duration_minutes: int = 60
    reminder_before: int = 15
    location: str = ""
    notes: str = ""


class TimetableEntryUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    subject: Optional[str] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = None
    reminder_before: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class TimetableEntryOut(BaseModel):
    id: str
    owner_id: str
    title: str
    subject: str = ""
    day_of_week: int
    time: str
    duration_minutes: int = 60
    reminder_before: int = 15
    location: str = ""
    notes: str = ""
