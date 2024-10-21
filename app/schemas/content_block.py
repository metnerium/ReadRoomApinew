from pydantic import BaseModel, Field


class StoryBlock(BaseModel):
    story_id: int
    user_id: int
    reason: str
    author_id: int
