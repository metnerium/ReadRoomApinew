from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models.story import Genre

class StoryBase(BaseModel):
    title: str
    summary: Optional[str] = None
    genre: Genre
    cover_image_url: Optional[str] = None

class StoryCreate(StoryBase):
    pass

class StoryUpdate(StoryBase):
    title: Optional[str] = None
    summary: Optional[str] = None
    genre: Optional[Genre] = None

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

class StoryListResponse(BaseModel):
    stories: List[StoryResponse]
    total: int
    page: int
    per_page: int

