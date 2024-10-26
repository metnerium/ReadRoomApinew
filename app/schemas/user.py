from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    vk_id: int
    full_name: str = Field(..., min_length=2, max_length=50)
    pseudonym: Optional[str] = Field(None, min_length=2, max_length=30)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(AUTHOR|ADMIN)$")

    @validator('full_name')
    def validate_full_name(cls, v):
        if not v.strip():
            raise ValueError('Full name cannot be empty or just whitespace')
        return v.strip()

    @validator('pseudonym')
    def validate_pseudonym(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError('Pseudonym cannot be empty or just whitespace')
            return v.strip()
        return v

class UserCreate(UserBase):
    url: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=50)
    pseudonym: Optional[str] = Field(None, min_length=2, max_length=30)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(AUTHOR|ADMIN)$")

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
