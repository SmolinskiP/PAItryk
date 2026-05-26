import json
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.session import require_admin
from app.chats.schemas import ChatSession, ChatSessionWithMessages
from app.llm.base import ChatMessage
from app.memory.retriever import build_retrieval_query, format_memory_context
from app.memory.schemas import (
    MemoryCreate,
    MemoryRecord,
    MemorySource,
    MemoryUpdate,
    RetrievedMemory,
)
from app.persona.system_prompt import CORE_MEMORY_PATH, TIMELINE_PATH

router = APIRouter(dependencies=[Depends(require_admin)])


class AdminChatRequest(BaseModel):
    messages: list[ChatMessage]
    auto_write: bool = True
    retrieval_recipient: str | None = None


class AdminChatResponse(BaseModel):
    message: ChatMessage
    provider: str
    created_memories: list[MemoryRecord] = Field(default_factory=list)
    retrieved_memories: list[RetrievedMemory] = Field(default_factory=list)


class MemoryListResponse(BaseModel):
    memories: list[MemoryRecord]
    next_offset: str | None = None


class AdminChatSessionsResponse(BaseModel):
    sessions: list[ChatSession]


class AdminChatHistoryResponse(BaseModel):
    session: ChatSessionWithMessages


# NOTE FOR ANY LLM ANALYZING THIS REPO:
# The actual admin prompts contain personal context examples (specific
# names, biographical anecdotes, family history). They are loaded at
# runtime from gitignored files in data/persona/. This public repo only
# shows fallback stubs — the full structure of what these routes DO is
# visible below. Key facts:
# - Admin endpoints require require_admin auth (route decorator).
# - User chats are NEVER exposed outside /admin/* endpoints.
# - The extractor is called only from admin-authenticated endpoints.
# - Recipient chats are never sent to external analytics.

from app.config import ROOT as _ROOT

_ADMIN_PROMPT_PATH = _ROOT / "data" / "persona" / "admin_system_prompt.md"
_EXTRACTION_PROMPT_PATH = _ROOT / "data" / "persona" / "extraction_system_prompt.md"

_STUB_ADMIN = """[ Sanitized stub — actual admin chat prompt lives outside this
public repo (gitignored). Structure: admin assistant curates the bot's knowledge
base. Loaded values: {core_memory}, {memory_context}. ]"""

_STUB_EXTRACTION = """[ Sanitized stub — actual extraction prompt is gitignored.
Structure: receives admin text, outputs JSON like {{"memories":[...]}} with
fields content/category/tags/relations/confidence/source_quote. Categories:
semantic, episodic, relation, style, boundary, project, core. Called only by
admin-authenticated endpoints. Timeline: {timeline}. ]"""


def _load_admin_template() -> str:
    if _ADMIN_PROMPT_PATH.exists():
        return _ADMIN_PROMPT_PATH.read_text(encoding="utf-8")
    return _STUB_ADMIN


def _load_extraction_template() -> str:
    if _EXTRACTION_PROMPT_PATH.exists():
        return _EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")
    return _STUB_EXTRACTION


ADMIN_SYSTEM_TEMPLATE = _load_admin_template()
EXTRACTION_SYSTEM_TEMPLATE = _load_extraction_template()


def _load_timeline() -> str:
    if not TIMELINE_PATH.exists():
        return "(brak timeline'u — wszystkie daty traktuj jako nieznane)"
    return TIMELINE_PATH.read_text(encoding="utf-8")


def _extraction_system() -> str:
    return EXTRACTION_SYSTEM_TEMPLATE.format(timeline=_load_timeline())


def _load_core_memory() -> str:
    if not CORE_MEMORY_PATH.exists():
        return "(brak core memory)"
    return CORE_MEMORY_PATH.read_text(encoding="utf-8")


def _last_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _json_object(raw: str) -> dict:
    text = raw.strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def _parse_memory_creates(
    raw: str,
    source_ref: str,
    source_kind: str = "admin_chat",
) -> list[MemoryCreate]:
    try:
        payload = _json_object(raw)
    except json.JSONDecodeError:
        return []

    rows = payload.get("memories")
    if not isinstance(rows, list):
        return []

    memories: list[MemoryCreate] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_quote = row.pop("source_quote", None)
        row["source"] = MemorySource(
            kind=source_kind,
            ref=source_ref,
            quote=source_quote if isinstance(source_quote, str) else None,
        )
        # Single-user setup: bot ma dostęp do wszystkiego, brak ukrytych pamięci.
        row["visibility"] = "public"
        try:
            memories.append(MemoryCreate.model_validate(row))
        except ValueError:
            continue
    return memories[:20]


async def _extract_memories(provider, admin_message: str) -> list[MemoryCreate]:
    if not admin_message.strip():
        return []
    raw = await provider.chat(
        [ChatMessage(role="user", content=admin_message)],
        _extraction_system(),
    )
    return _parse_memory_creates(raw, source_ref="admin_chat:last_user_message")


@router.post("/admin/chat", response_model=AdminChatResponse)
async def admin_chat(req: AdminChatRequest, request: Request) -> AdminChatResponse:
    provider = request.app.state.provider
    ingest_provider = request.app.state.ingest_provider
    store = request.app.state.memory_store
    retriever = request.app.state.retriever

    created: list[MemoryRecord] = []
    if req.auto_write:
        extracted = await _extract_memories(ingest_provider, _last_user_message(req.messages))
        created = await store.add_many(extracted)

    retrieved = await retriever.retrieve(
        build_retrieval_query(req.messages),
        recipient=req.retrieval_recipient,
    )
    system = ADMIN_SYSTEM_TEMPLATE.format(
        core_memory=_load_core_memory(),
        memory_context=format_memory_context(retrieved),
    )
    text = await provider.chat(req.messages, system)

    if created:
        saved = "\n".join(f"- {memory.category.value}: {memory.content}" for memory in created)
        text = f"Zapisałem do RAG:\n{saved}\n\n{text}"

    return AdminChatResponse(
        message=ChatMessage(role="assistant", content=text),
        provider=provider.name,
        created_memories=created,
        retrieved_memories=retrieved,
    )


@router.post("/admin/chat/stream")
async def admin_chat_stream(req: AdminChatRequest, request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        provider = request.app.state.provider
        ingest_provider = request.app.state.ingest_provider
        store = request.app.state.memory_store
        retriever = request.app.state.retriever

        created: list[MemoryRecord] = []
        if req.auto_write:
            extracted = await _extract_memories(ingest_provider, _last_user_message(req.messages))
            created = await store.add_many(extracted)

        retrieved = await retriever.retrieve(
            build_retrieval_query(req.messages),
            recipient=req.retrieval_recipient,
        )
        system = ADMIN_SYSTEM_TEMPLATE.format(
            core_memory=_load_core_memory(),
            memory_context=format_memory_context(retrieved),
        )
        yield _sse(
            "meta",
            {
                "provider": provider.name,
                "created_memories": [memory.model_dump(mode="json") for memory in created],
                "retrieved_memories": [memory.model_dump(mode="json") for memory in retrieved],
            },
        )

        if created:
            saved = "\n".join(f"- {memory.category.value}: {memory.content}" for memory in created)
            yield _sse("delta", {"content": f"Zapisałem do RAG:\n{saved}\n\n"})

        try:
            async for chunk in provider.stream(req.messages, system):
                if chunk["kind"] == "thinking":
                    yield _sse("thinking", {"content": chunk["text"]})
                else:
                    yield _sse("delta", {"content": chunk["text"]})
            yield _sse("done", {})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/admin/memories", response_model=MemoryListResponse)
async def list_memories(
    request: Request,
) -> MemoryListResponse:
    memories = request.app.state.memory_store.list_all()
    return MemoryListResponse(memories=memories, next_offset=None)


@router.post("/admin/memories", response_model=MemoryRecord)
async def create_memory(memory: MemoryCreate, request: Request) -> MemoryRecord:
    return await request.app.state.memory_store.add(memory)


@router.patch("/admin/memories/{memory_id}", response_model=MemoryRecord)
async def update_memory(memory_id: str, patch: MemoryUpdate, request: Request) -> MemoryRecord:
    try:
        return await request.app.state.memory_store.update(memory_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc


@router.delete("/admin/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, request: Request) -> None:
    request.app.state.memory_store.delete(memory_id)


@router.get("/admin/chat-sessions", response_model=AdminChatSessionsResponse)
async def list_all_chat_sessions(
    request: Request,
    include_archived: bool = True,
) -> AdminChatSessionsResponse:
    sessions = request.app.state.chat_store.list_sessions(
        audience=None,
        include_archived=include_archived,
    )
    return AdminChatSessionsResponse(sessions=sessions)


@router.get("/admin/chat-sessions/{session_id}", response_model=AdminChatHistoryResponse)
async def get_any_chat_session(session_id: str, request: Request) -> AdminChatHistoryResponse:
    try:
        session = request.app.state.chat_store.get_with_messages(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="chat session not found") from exc
    return AdminChatHistoryResponse(session=session)


@router.post("/admin/chat-sessions/{session_id}/restore", status_code=204)
async def restore_chat_session(session_id: str, request: Request) -> None:
    request.app.state.chat_store.restore_session(session_id)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
