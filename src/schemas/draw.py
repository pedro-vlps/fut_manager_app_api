from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class DrawSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    use_positions: bool = False
    use_ratings: bool = False
    use_wins: bool = False


class RatingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: Decimal | None = Field(ge=0, le=10, max_digits=3, decimal_places=1)


class RatingView(BaseModel):
    rating: float | None
