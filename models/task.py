from typing import Optional
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    priority: str = "medium"
    due_date: str = ""
    due_time: str = ""
    reminder_minutes: int = 0
    category: str = "general"
    notes: str = ""
    completed: bool = False


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    priority: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    reminder_minutes: Optional[int] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    completed: Optional[bool] = None


class TaskOut(BaseModel):
    id: str
    owner_id: str
    title: str
    priority: str = "medium"
    due_date: str = ""
    due_time: str = ""
    reminder_minutes: int = 0
    category: str = "general"
    notes: str = ""
    completed: bool = False
    created_at: str = ""
