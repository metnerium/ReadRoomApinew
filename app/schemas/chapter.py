from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ChapterBase(BaseModel):
    title: str
    content: str
    chapter_number: int

class ChapterCreate(ChapterBase):
    story_id: int

class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class ChapterInDB(ChapterBase):
    id: int
    story_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True