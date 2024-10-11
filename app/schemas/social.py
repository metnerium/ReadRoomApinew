from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    story_id: int

class CommentUpdate(CommentBase):
    pass

class CommentResponse(CommentBase):
    id: int
    user_id: int
    story_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    user_name: str

    class Config:
        from_attributes = True

class LikeCreate(BaseModel):
    story_id: int

class LikeResponse(BaseModel):
    id: int
    user_id: int
    story_id: int
    created_at: datetime
    likes_count: int

    class Config:
        from_attributes = True

class BookmarkCreate(BaseModel):
    story_id: int
    last_read_chapter: Optional[int] = None

class BookmarkUpdate(BaseModel):
    last_read_chapter: int

class BookmarkResponse(BaseModel):
    id: int
    user_id: int
    story_id: int
    created_at: datetime
    last_read_chapter: Optional[int] = None
    bookmarks_count: int

    class Config:
        from_attributes = True

class UserFollowCreate(BaseModel):
    followed_id: int

class UserFollowResponse(BaseModel):
    id: int
    follower_id: int
    followed_id: int
    created_at: datetime
    follower_name: str
    followed_name: str
    follower_count: int

    class Config:
        from_attributes = True