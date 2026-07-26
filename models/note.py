from typing import Optional, List
from pydantic import BaseModel, Field


class NoteAttachment(BaseModel):
    filename: str = ""
    type: str = ""
    uri: str = ""
    mimeType: str = ""
    size: int = 0
    duration: int = 0


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = ""
    subject: str = ""
    note_type: str = "text"
    attachments: List[NoteAttachment] = []
    pinned: bool = False


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    content: Optional[str] = None
    subject: Optional[str] = None
    note_type: Optional[str] = None
    attachments: Optional[List[NoteAttachment]] = None
    pinned: Optional[bool] = None


class NoteOut(BaseModel):
    id: str
    owner_id: str
    title: str
    content: str = ""
    subject: str = ""
    note_type: str = "text"
    attachments: List[NoteAttachment] = []
    pinned: bool = False
    created_at: str = ""
    updated_at: str = ""
