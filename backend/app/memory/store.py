from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.memory.embeddings import OllamaEmbedder
from app.memory.schemas import (
    MemoryCreate,
    MemoryRecord,
    MemoryUpdate,
    RetrievedMemory,
)


class MemoryStore:
    def __init__(
        self,
        path: str,
        collection_name: str,
        embedder: OllamaEmbedder,
    ):
        self.client = QdrantClient(path=str(Path(path)))
        self.collection_name = collection_name
        self.embedder = embedder

    async def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        probe = await self.embedder.embed("PAItryk memory vector dimension probe")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=len(probe), distance=Distance.COSINE),
        )
        for field_name in ("category", "visibility", "relations", "tags"):
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )

    async def add(self, memory: MemoryCreate) -> MemoryRecord:
        await self.ensure_collection()
        record = MemoryRecord.model_validate(memory.model_dump())
        vector = await self.embedder.embed(record.searchable_text())
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=record.id,
                    vector=vector,
                    payload=record.to_payload(),
                )
            ],
        )
        return record

    async def add_many(self, memories: list[MemoryCreate]) -> list[MemoryRecord]:
        if not memories:
            return []
        await self.ensure_collection()
        records = [MemoryRecord.model_validate(memory.model_dump()) for memory in memories]
        vectors = await self.embedder.embed_many([record.searchable_text() for record in records])
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(id=record.id, vector=vector, payload=record.to_payload())
                for record, vector in zip(records, vectors, strict=True)
            ],
        )
        return records

    async def update(self, memory_id: str, patch: MemoryUpdate) -> MemoryRecord:
        await self.ensure_collection()
        existing = self.get(memory_id)
        data = existing.model_dump()
        patch_data = patch.model_dump(exclude_unset=True)
        data.update({key: value for key, value in patch_data.items() if value is not None})
        data["updated_at"] = datetime.now(UTC)
        record = MemoryRecord.model_validate(data)
        vector = await self.embedder.embed(record.searchable_text())
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=record.id, vector=vector, payload=record.to_payload())],
        )
        return record

    def get(self, memory_id: str) -> MemoryRecord:
        if not self.client.collection_exists(self.collection_name):
            raise KeyError(memory_id)
        records = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[memory_id],
            with_payload=True,
            with_vectors=False,
        )
        if not records or records[0].payload is None:
            raise KeyError(memory_id)
        return MemoryRecord.from_payload(records[0].payload)

    def delete(self, memory_id: str) -> None:
        if not self.client.collection_exists(self.collection_name):
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[memory_id]),
        )

    def list(
        self,
        limit: int = 100,
        offset: str | None = None,
    ) -> tuple[list[MemoryRecord], str | None]:
        if not self.client.collection_exists(self.collection_name):
            return [], None
        records, next_offset = self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        memories = [
            MemoryRecord.from_payload(record.payload)
            for record in records
            if record.payload is not None
        ]
        return memories, str(next_offset) if next_offset is not None else None

    def list_all(self) -> list[MemoryRecord]:
        if not self.client.collection_exists(self.collection_name):
            return []
        all_memories: list[MemoryRecord] = []
        offset = None
        while True:
            batch, next_offset = self.list(limit=500, offset=offset)
            all_memories.extend(batch)
            if next_offset is None:
                break
            offset = next_offset
        return all_memories

    async def search(
        self,
        query: str,
        *,
        recipient: str | None,
        limit: int,
        score_threshold: float | None = None,
    ) -> list[RetrievedMemory]:
        # Single-user setup — brak filtrowania widoczności. Bot ma 100% dostęp.
        # `recipient` zostaje w sygnaturze dla forward-compat, ale jest ignorowany.
        del recipient
        await self.ensure_collection()
        vector = await self.embedder.embed(query)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            score_threshold=score_threshold,
        )
        return [
            RetrievedMemory(
                memory=MemoryRecord.from_payload(point.payload),
                vector_score=point.score,
            )
            for point in response.points
            if point.payload is not None
        ]
