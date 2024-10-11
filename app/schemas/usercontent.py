from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models.story import Genre


class UserStoryResponse(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    genre: Genre
    cover_image_url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    likes_count: int
    bookmarks_count: int
    views: int
    rating: float

    class Config:
        from_attributes = True
