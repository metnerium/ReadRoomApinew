from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    vk_id: int
    full_name: str
    pseudonym: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None

class UserCreate(UserBase):
    vk_id: int
    url: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    pseudonym: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None

class UserInDB(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserProfile(UserInDB):
    followers_count: int
    following_count: int
    stories_count: int

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    vk_id: Optional[int] = None

class UserLogin(BaseModel):
    url: str
    vk_id: int
