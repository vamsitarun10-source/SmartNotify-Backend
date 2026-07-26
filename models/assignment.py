from typing import Optional
from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=1)
    subject: str = ""
    due_date: str = ""
    due_time: str = "23:59"
    priority: str = "medium"
    notes: str = ""
    attachment: str = ""
    reminder_minutes: int = 0
    completed: bool = False


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    subject: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    attachment: Optional[str] = None
    reminder_minutes: Optional[int] = None
    completed: Optional[bool] = None


class AssignmentOut(BaseModel):
    id: str
    owner_id: str
    title: str
    subject: str = ""
    due_date: str = ""
    due_time: str = "23:59"
    priority: str = "medium"
    notes: str = ""
    attachment: str = ""
    reminder_minutes: int = 0
    completed: bool = False
    created_at: str = ""
