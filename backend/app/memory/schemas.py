from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MemoryCategory(StrEnum):
    CORE = "core"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    RELATION = "relation"
    STYLE = "style"
    BOUNDARY = "boundary"
    PROJECT = "project"


class VisibilityScope(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    PER_RELATION = "per_relation"


class MemorySource(BaseModel):
    kind: str = Field(description="Source type, e.g. admin_chat, therapy_note, email")
    ref: str | None = Field(default=None, description="Source reference or document name")
    quote: str | None = Field(default=None, description="Short source quote if useful")


class MemoryCreate(BaseModel):
    content: str
    category: MemoryCategory
    tags: list[str] = Field(default_factory=list)
    visibility: VisibilityScope = VisibilityScope.PUBLIC
    relations: list[str] = Field(default_factory=list)
    source: MemorySource = Field(default_factory=lambda: MemorySource(kind="manual"))
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content cannot be blank")
        return value

    @field_validator("tags", "relations")
    @classmethod
    def normalize_list(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().lower() for item in value if item.strip()})


class MemoryUpdate(BaseModel):
    content: str | None = None
    category: MemoryCategory | None = None
    tags: list[str] | None = None
    visibility: VisibilityScope | None = None
    relations: list[str] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("content cannot be blank")
        return value

    @field_validator("tags", "relations")
    @classmethod
    def normalize_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({item.strip().lower() for item in value if item.strip()})


class MemoryRecord(MemoryCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def searchable_text(self) -> str:
        tags = ", ".join(self.tags) if self.tags else "brak"
        relations = ", ".join(self.relations) if self.relations else "brak"
        return (
            f"Kategoria: {self.category.value}\n"
            f"Tagi: {tags}\n"
            f"Relacje: {relations}\n"
            f"Treść: {self.content}"
        )

    def to_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["searchable_text"] = self.searchable_text()
        return data

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MemoryRecord":
        clean = {k: v for k, v in payload.items() if k != "searchable_text"}
        return cls.model_validate(clean)


class RetrievedMemory(BaseModel):
    memory: MemoryRecord
    vector_score: float
    rerank_score: float | None = None

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.vector_score
