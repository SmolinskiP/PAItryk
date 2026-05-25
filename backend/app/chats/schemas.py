from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.llm.base import ChatMessage

ChatAudience = Literal["public", "admin"]


class ChatSession(BaseModel):
    id: str
    audience: ChatAudience
    title: str
    archived: bool
    created_at: datetime
    updated_at: datetime


class ChatSessionWithMessages(ChatSession):
    messages: list[ChatMessage]
