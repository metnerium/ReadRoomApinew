from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from app.models.story import Genre
class StoryBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    summary: Optional[str] = Field(None, max_length=500)
    genre: Genre
    cover_image_url: Optional[str] = None

class StoryCreate(StoryBase):
    pass

class StoryUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    summary: Optional[str] = Field(None, max_length=500)
    genre: Optional[Genre] = None
    cover_image_url: Optional[str] = None

class StoryResponse(StoryBase):
    id: int
    author_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    author_name: str
    author_avatar_url: Optional[str] = None
    likes_count: int
    bookmarks_count: int
    rating: float
    views: int
    is_liked: bool
    is_bookmarked: bool
    is_following_author: bool
    is_my_story: bool
    follower_count: int

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class StoryListResponse(BaseModel):
    stories: List[StoryResponse]
    total: int
    page: int
    per_page: int
