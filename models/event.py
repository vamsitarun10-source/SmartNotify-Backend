from typing import Optional

from pydantic import BaseModel, Field


class ClassEvent(BaseModel):
    title: str = Field(..., min_length=1)
    subject: str = ""
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    reminder_before: int = 15
    location: str = ""
    notes: str = ""
    completed: bool = False
    duration_minutes: Optional[int] = None


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1)
    subject: str = ""
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    reminder_before: int = 15
    location: str = ""
    notes: str = ""
    completed: bool = False
    duration_minutes: Optional[int] = None


class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    subject: Optional[str] = None
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    reminder_before: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    completed: Optional[bool] = None
    attended: Optional[bool] = None
    duration_minutes: Optional[int] = None


class EventOut(BaseModel):
    id: str
    owner_id: str
    title: str
    subject: str = ""
    date: str
    time: str
    reminder_before: int = 15
    location: str = ""
    notes: str = ""
    completed: bool = False
    attended: Optional[bool] = None
    duration_minutes: Optional[int] = None
