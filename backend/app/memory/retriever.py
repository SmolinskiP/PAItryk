import json
import re

import ollama

from app.memory.schemas import RetrievedMemory
from app.memory.store import MemoryStore


class OllamaReranker:
    def __init__(self, host: str, model: str):
        self.client = ollama.AsyncClient(host=host)
        self.model = model

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedMemory],
        limit: int,
    ) -> list[RetrievedMemory]:
        if not candidates:
            return []

        payload = [
            {
                "id": item.memory.id,
                "category": item.memory.category.value,
                "tags": item.memory.tags,
                "content": item.memory.content,
            }
            for item in candidates
        ]
        response = await self.client.chat(
            model=self.model,
            format="json",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Jesteś rerankerem pamięci RAG. Oceń, które wspomnienia są "
                        "najbardziej przydatne do odpowiedzi na zapytanie. Zwróć wyłącznie "
                        "JSON: {\"scores\":[{\"id\":\"...\",\"score\":0.0-1.0}]}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Zapytanie:\n{query}\n\n"
                        f"Kandydaci JSON:\n{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        scores = self._parse_scores(response["message"]["content"])
        if not scores:
            return sorted(candidates, key=lambda item: item.vector_score, reverse=True)[:limit]

        by_id = {item.memory.id: item for item in candidates}
        ranked: list[RetrievedMemory] = []
        for memory_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            item = by_id.get(memory_id)
            if item is None:
                continue
            ranked.append(item.model_copy(update={"rerank_score": score}))

        seen = {item.memory.id for item in ranked}
        ranked.extend(
            item for item in sorted(candidates, key=lambda item: item.vector_score, reverse=True)
            if item.memory.id not in seen
        )
        return ranked[:limit]

    def _parse_scores(self, raw: str) -> dict[str, float]:
        text = raw.strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}

        rows = payload.get("scores") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return {}

        scores: dict[str, float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            memory_id = row.get("id")
            score = row.get("score")
            if not isinstance(memory_id, str) or not isinstance(score, int | float):
                continue
            scores[memory_id] = max(0.0, min(1.0, float(score)))
        return scores


class Retriever:
    def __init__(
        self,
        store: MemoryStore,
        search_limit: int,
        context_limit: int,
        score_threshold: float,
    ):
        self.store = store
        self.search_limit = search_limit
        self.context_limit = context_limit
        self.score_threshold = score_threshold

    async def retrieve(self, query: str, *, recipient: str | None) -> list[RetrievedMemory]:
        candidates = await self.store.search(
            query,
            recipient=recipient,
            limit=self.search_limit,
            score_threshold=self.score_threshold,
        )
        return self._diverse_select(candidates, self.context_limit)

    def _diverse_select(self, candidates: list[RetrievedMemory], limit: int) -> list[RetrievedMemory]:
        """Interleave episodic and non-episodic so specific events always reach context."""
        episodic = sorted(
            [m for m in candidates if m.memory.category.value == "episodic"],
            key=lambda m: m.vector_score, reverse=True,
        )
        other = sorted(
            [m for m in candidates if m.memory.category.value != "episodic"],
            key=lambda m: m.vector_score, reverse=True,
        )
        result: list[RetrievedMemory] = []
        i = j = 0
        while len(result) < limit and (i < len(episodic) or j < len(other)):
            if i < len(episodic):
                result.append(episodic[i]); i += 1
            if len(result) < limit and j < len(other):
                result.append(other[j]); j += 1
        return result


def build_retrieval_query(messages: list) -> str:
    recent = messages[-6:]
    return "\n".join(f"{message.role}: {message.content}" for message in recent)


def format_memory_context(memories: list[RetrievedMemory]) -> str:
    if not memories:
        return "(brak trafionych wspomnień w RAG)"

    blocks = []
    for index, item in enumerate(memories, start=1):
        memory = item.memory
        score = item.final_score
        tags = ", ".join(memory.tags) if memory.tags else "brak"
        relations = ", ".join(memory.relations) if memory.relations else "brak"
        blocks.append(
            f"[{index}] id={memory.id} score={score:.3f} "
            f"category={memory.category.value} tags={tags} relations={relations}\n"
            f"{memory.content}"
        )
    return "\n\n".join(blocks)
