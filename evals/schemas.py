from pydantic import (
    BaseModel,
    Field,
)


class ScoreSchema(BaseModel):
    score: float = Field(description="provide a score between 0 and 1")
    reasoning: str = Field(description="provide a one sentence reasoning")
