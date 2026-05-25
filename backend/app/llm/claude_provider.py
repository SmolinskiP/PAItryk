from collections.abc import AsyncIterator

import anthropic

from .base import ChatMessage, LLMProvider, StreamChunk


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", thinking_budget: int = 0):
        self.client = (
            anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        )
        self.model = model
        self.thinking_budget = thinking_budget

    def _build_kwargs(self, messages: list[ChatMessage], system: str) -> dict:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 64000,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if self.thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
        return kwargs

    async def chat(self, messages: list[ChatMessage], system: str) -> str:
        response = await self.client.messages.create(**self._build_kwargs(messages, system))
        return next(b.text for b in response.content if b.type == "text")

    async def stream(
        self, messages: list[ChatMessage], system: str
    ) -> AsyncIterator[StreamChunk]:
        async with self.client.messages.stream(**self._build_kwargs(messages, system)) as stream:
            if self.thinking_budget > 0:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "thinking_delta":
                            yield {"kind": "thinking", "text": delta.thinking}
                        elif delta.type == "text_delta" and delta.text:
                            yield {"kind": "content", "text": delta.text}
            else:
                async for text in stream.text_stream:
                    if text:
                        yield {"kind": "content", "text": text}
