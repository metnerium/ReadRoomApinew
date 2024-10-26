from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, UniqueConstraint, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from database import Base

class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="likes")
    story = relationship("Story", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("user_id", "story_id", name="unique_user_story_like"),
    )

class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    last_read_chapter = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="bookmarks")
    story = relationship("Story", back_populates="bookmarks")

    # Оптимизированные индексы
    __table_args__ = (
        Index('idx_bookmark_user_stories', user_id, story_id),
        Index('idx_bookmark_story_created', story_id, created_at.desc()),
        Index('idx_bookmark_user_created', user_id, created_at.desc()),
        {'postgresql_partition_by': 'RANGE (created_at)'} # Партиционирование по дате
    )

class UserFollow(Base):
    __tablename__ = "user_follows"

    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    followed_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    followed = relationship("User", foreign_keys=[followed_id], back_populates="followers")

    __table_args__ = (
        UniqueConstraint("follower_id", "followed_id", name="unique_user_follow"),
    )


# Дополнительные индексы для оптимизации запросов
Index("ix_likes_story_id", Like.story_id)  # Для быстрого подсчета лайков
Index("ix_bookmarks_story_id", Bookmark.story_id)  # Для быстрого подсчета закладок
Index("ix_user_follows_followed_id", UserFollow.followed_id)  # Для быстрого подсчета подписчиков