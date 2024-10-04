from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    story_id: int

class CommentUpdate(BaseModel):
    content: str

class CommentInDB(CommentBase):
    id: int
    user_id: int
    story_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CommentResponse(CommentInDB):
    user_name: str

class LikeCreate(BaseModel):
    story_id: int

class LikeInDB(LikeCreate):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class BookmarkCreate(BaseModel):
    story_id: int
    last_read_chapter: Optional[int] = None

class BookmarkUpdate(BaseModel):
    last_read_chapter: int

class BookmarkInDB(BookmarkCreate):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class UserFollowCreate(BaseModel):
    followed_id: int

class UserFollowInDB(UserFollowCreate):
    id: int
    follower_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class UserFollowResponse(UserFollowInDB):
    follower_name: str
    followed_name: str
