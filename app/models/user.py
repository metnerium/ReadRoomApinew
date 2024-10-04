from sqlalchemy import Column, Integer, String, Enum, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

class UserRole(enum.Enum):
    READER = "reader"
    AUTHOR = "author"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    pseudonym = Column(String, unique=True, nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.READER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    stories = relationship("Story", back_populates="author")
    comments = relationship("Comment", back_populates="user")
    likes = relationship("Like", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")
    followers = relationship("UserFollow", foreign_keys="UserFollow.followed_id", back_populates="followed")
    following = relationship("UserFollow", foreign_keys="UserFollow.follower_id", back_populates="follower")
