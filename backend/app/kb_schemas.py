"""Knowledge-base request and response models. Bodies are plain text (rendered, never as HTML)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Visibility = Literal["internal", "client"]
KbStatus = Literal["draft", "published", "archived"]
MAX_TAGS = 10
SNIPPET_CHARS = 200


def snippet_of(body: str) -> str:
    return body[:SNIPPET_CHARS]


def _clean_tags(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        t = tag.strip().lower()
        if not 1 <= len(t) <= 40:
            raise ValueError("Each tag must be 1 to 40 characters")
        seen.setdefault(t)
    return list(seen)


class _Text(BaseModel):
    @field_validator("title", "body", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class KbArticleIn(_Text):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50_000)
    visibility: Visibility
    status: KbStatus = "draft"
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return _clean_tags(v)


class KbArticlePatch(_Text):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=50_000)
    visibility: Visibility | None = None
    status: KbStatus | None = None
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return None if v is None else _clean_tags(v)


class KbArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    visibility: Visibility
    status: KbStatus
    tags: list[str]
    created_by_name: str | None = None
    updated_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class KbArticleSummary(BaseModel):
    id: int
    title: str
    visibility: Visibility
    status: KbStatus
    tags: list[str]
    updated_at: datetime
    snippet: str


class PortalKbSummary(BaseModel):
    id: int
    title: str
    tags: list[str]
    updated_at: datetime
    snippet: str


class PortalKbArticleOut(BaseModel):
    id: int
    title: str
    body: str
    tags: list[str]
    updated_at: datetime
