from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

class Genre(enum.Enum):
    FICTION = "fiction"
    NON_FICTION = "non-fiction"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    SCIFI = "science_fiction"
    FANTASY = "fantasy"
    HORROR = "horror"
    POETRY = "poetry"
    THOUGHTS = "thoughts"
    IDEAS = "ideas"

class Story(Base):
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    summary = Column(Text, nullable=True)
    genre = Column(Enum(Genre))
    cover_image_url = Column(String, nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    rating = Column(Float, default=0.0)
    views = Column(Integer, default=0)

    author = relationship("User", back_populates="stories")
    chapters = relationship("Chapter", back_populates="story")
    comments = relationship("Comment", back_populates="story")
    likes = relationship("Like", back_populates="story")
    bookmarks = relationship("Bookmark", back_populates="story")