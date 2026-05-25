from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from .base import ChatMessage, LLMProvider, StreamChunk


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    def _messages(self, messages: list[ChatMessage], system: str) -> list[dict]:
        return [
            {"role": "system", "content": system},
            *[{"role": m.role, "content": m.content} for m in messages],
        ]

    async def chat(self, messages: list[ChatMessage], system: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            reasoning_effort="medium",
            messages=self._messages(messages, system),
        )
        return response.choices[0].message.content or ""

    async def stream(
        self, messages: list[ChatMessage], system: str
    ) -> AsyncIterator[StreamChunk]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            reasoning_effort="medium",
            messages=self._messages(messages, system),
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content if chunk.choices else None
            if text:
                yield {"kind": "content", "text": text}
