from typing import Literal
from typing import Self

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ExternalModel(BaseModel):
    """A tolerant model for alphaXiv-owned response payloads."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class StrictModel(BaseModel):
    """A strict model for CLI-owned inputs and stable outputs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RestSettings(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: Literal["https://api.alphaxiv.org"] = "https://api.alphaxiv.org"
    timeout_seconds: float = Field(default=20.0, gt=0, le=120)


class ErrorDetail(StrictModel):
    code: str
    message: str


class ErrorEnvelope(StrictModel):
    error: ErrorDetail


class ItemCollection[ItemT: BaseModel](StrictModel):
    items: list[ItemT]
    count: int = Field(ge=0)

    @classmethod
    def from_items(cls, items: list[ItemT]) -> Self:
        return cls(items=items, count=len(items))
