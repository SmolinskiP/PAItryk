from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal, TypedDict

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class StreamChunk(TypedDict):
    kind: Literal["thinking", "content"]
    text: str


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], system: str) -> str: ...

    @abstractmethod
    def stream(
        self, messages: list[ChatMessage], system: str
    ) -> AsyncIterator[StreamChunk]: ...
