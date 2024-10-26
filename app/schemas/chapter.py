from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ChapterBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)
    chapter_number: int = Field(..., gt=0)

class ChapterCreate(ChapterBase):
    story_id: int = Field(..., gt=0)

class ChapterUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    content: Optional[str] = Field(None, min_length=1)

class ChapterInDB(ChapterBase):
    id: int
    story_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True