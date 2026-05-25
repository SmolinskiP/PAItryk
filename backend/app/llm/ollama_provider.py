from collections.abc import AsyncIterator

import ollama

from .base import ChatMessage, LLMProvider, StreamChunk


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, host: str, model: str):
        self.client = ollama.AsyncClient(host=host)
        self.model = model

    async def chat(self, messages: list[ChatMessage], system: str) -> str:
        response = await self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                *({"role": m.role, "content": m.content} for m in messages),
            ],
        )
        return response["message"]["content"]

    async def stream(
        self, messages: list[ChatMessage], system: str
    ) -> AsyncIterator[StreamChunk]:
        stream = await self.client.chat(
            model=self.model,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                *({"role": m.role, "content": m.content} for m in messages),
            ],
        )
        async for chunk in stream:
            message = chunk.get("message", {})
            thinking = message.get("thinking")
            if thinking:
                yield {"kind": "thinking", "text": thinking}
            content = message.get("content")
            if content:
                yield {"kind": "content", "text": content}
