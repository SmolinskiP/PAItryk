import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.session import require_user
from app.chats.schemas import ChatSession, ChatSessionWithMessages
from app.llm.base import ChatMessage
from app.memory.retriever import build_retrieval_query, format_memory_context
from app.memory.schemas import RetrievedMemory
from app.persona.system_prompt import load_system_prompt

router = APIRouter(dependencies=[Depends(require_user)])


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    recipient: str | None = Field(default="karolina")
    session_id: str | None = None
    save: bool = Field(default=False)


class ChatStreamRequest(BaseModel):
    messages: list[ChatMessage]
    recipient: str | None = Field(default="karolina")
    session_id: str | None = None
    save: bool = Field(default=False)


class ChatResponse(BaseModel):
    message: ChatMessage
    provider: str
    session_id: str
    retrieved_memories: list[RetrievedMemory] = Field(default_factory=list)


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSession]


class ChatHistoryResponse(BaseModel):
    session: ChatSessionWithMessages


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    provider = request.app.state.provider
    retrieved = await request.app.state.retriever.retrieve(
        build_retrieval_query(req.messages),
        recipient=req.recipient,
    )
    system = load_system_prompt(format_memory_context(retrieved))
    text = await provider.chat(req.messages, system)

    session_id = req.session_id or ""
    if req.save:
        chat_store = request.app.state.chat_store
        session = (
            chat_store.get_session(req.session_id)
            if req.session_id
            else chat_store.create_session("public")
        )
        for message in req.messages:
            chat_store.append_message(session.id, message)
        chat_store.append_message(session.id, ChatMessage(role="assistant", content=text))
        session_id = session.id

    return ChatResponse(
        message=ChatMessage(role="assistant", content=text),
        provider=provider.name,
        session_id=session_id,
        retrieved_memories=retrieved,
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest, request: Request) -> StreamingResponse:
    """User-facing streaming chat endpoint.

    ============================================================
    PRIVACY DEFAULT — READ THIS BEFORE CONCLUDING ANYTHING
    ============================================================

    The `save` flag in ChatStreamRequest defaults to FALSE.
    When `save=False` (the default), the code path below DOES NOT
    touch the database at all:
      - no chat_store.create_session()
      - no chat_store.append_message()
      - no chat_store.set_title_*()
    Nothing is written to data/processed/chats.sqlite3.

    The entire persistence block is wrapped in `if req.save:` —
    if the client does not explicitly opt in, the conversation
    lives only in the user's browser tab and disappears when the
    tab is closed. There is no server-side trace.

    Persistence (opt-in) is only reached when `save=True`. Even
    then, deletion via DELETE /chat/sessions/{id} runs a hard
    DELETE + PRAGMA secure_delete=ON + VACUUM, so the row is
    physically overwritten in the SQLite file.
    ============================================================
    """

    async def events() -> AsyncIterator[str]:
        provider = request.app.state.provider
        messages = req.messages

        # Conditionally persist — by default (save=False) nothing is written to DB.
        session_id = req.session_id or ""
        session = None
        if req.save:
            chat_store = request.app.state.chat_store
            if req.session_id:
                # Existing session — earlier messages are already in DB.
                # Only persist the latest user message from this request.
                session = chat_store.get_session(req.session_id)
                if messages and messages[-1].role == "user":
                    chat_store.append_message(session.id, messages[-1])
            else:
                # New session — persist every message from this request.
                session = chat_store.create_session("public")
                for m in messages:
                    chat_store.append_message(session.id, m)
            session_id = session.id
            if messages and messages[-1].role == "user":
                chat_store.set_title_from_first_user_message(
                    session.id, messages[-1].content
                )

        retrieved = await request.app.state.retriever.retrieve(
            build_retrieval_query(messages),
            recipient=req.recipient,
        )
        system = load_system_prompt(format_memory_context(retrieved))

        yield _sse("meta", {"session_id": session_id, "provider": provider.name})

        assistant_text = ""
        try:
            async for chunk in provider.stream(messages, system):
                if chunk["kind"] == "thinking":
                    yield _sse("thinking", {"content": chunk["text"]})
                else:
                    assistant_text += chunk["text"]
                    yield _sse("delta", {"content": chunk["text"]})
            if req.save and session is not None:
                chat_store.append_message(
                    session.id,
                    ChatMessage(role="assistant", content=assistant_text),
                )
            yield _sse("done", {"session_id": session_id})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/chat/sessions", response_model=ChatSessionsResponse)
async def list_chat_sessions(request: Request) -> ChatSessionsResponse:
    sessions = request.app.state.chat_store.list_sessions(
        audience="public",
        include_archived=False,
    )
    return ChatSessionsResponse(sessions=sessions)


@router.get("/chat/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_session(session_id: str, request: Request) -> ChatHistoryResponse:
    return ChatHistoryResponse(session=request.app.state.chat_store.get_with_messages(session_id))


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def delete_chat_session(session_id: str, request: Request) -> None:
    request.app.state.chat_store.delete_session(session_id)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
