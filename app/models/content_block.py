from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
class Block(Base):
    __tablename__ = "content_block"

    story_id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    reason = Column(Text)
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    author = relationship("User", back_populates="stories")
