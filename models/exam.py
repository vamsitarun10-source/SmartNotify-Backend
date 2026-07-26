from typing import Optional
from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    title: str = Field(..., min_length=1)
    subject: str = ""
    exam_type: str = "internal"
    date: str = ""
    time: str = "09:00"
    duration_minutes: int = 120
    location: str = ""
    notes: str = ""
    reminder_minutes: int = 30


class ExamUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    subject: Optional[str] = None
    exam_type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    reminder_minutes: Optional[int] = None
    completed: Optional[bool] = None


class ExamOut(BaseModel):
    id: str
    owner_id: str
    title: str
    subject: str = ""
    exam_type: str = "internal"
    date: str = ""
    time: str = "09:00"
    duration_minutes: int = 120
    location: str = ""
    notes: str = ""
    reminder_minutes: int = 30
    completed: bool = False
    created_at: str = ""
