from pydantic import BaseModel, Field


class StoryBlock(BaseModel):
    story_id: int
    reason: str
