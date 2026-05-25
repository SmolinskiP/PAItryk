from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_chat import router as admin_chat_router
from app.api.admin_ingest import router as admin_ingest_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.models import router as models_router
from app.auth.store import UserStore
from app.chats.store import ChatStore
from app.config import get_frontend_origins, settings
from app.llm.base import LLMProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAIProvider
from app.memory.embeddings import OllamaEmbedder
from app.memory.retriever import Retriever
from app.memory.store import MemoryStore


def make_provider() -> LLMProvider:
    if settings.chat_provider == "claude":
        return ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model, thinking_budget=settings.anthropic_thinking_budget)
    if settings.chat_provider == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    return OllamaProvider(host=settings.ollama_host, model=settings.ollama_chat_model)


def make_ingest_provider() -> LLMProvider:
    if settings.ingest_provider == "claude":
        return ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    if settings.ingest_provider == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    return OllamaProvider(host=settings.ollama_host, model=settings.ollama_ingest_model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.provider = make_provider()
    app.state.ingest_provider = make_ingest_provider()
    app.state.chat_store = ChatStore(settings.chat_db_path)
    app.state.user_store = UserStore(settings.auth_db_path)
    embedder = OllamaEmbedder(host=settings.ollama_host, model=settings.ollama_embed_model)
    app.state.memory_store = MemoryStore(
        path=settings.qdrant_path,
        collection_name=settings.qdrant_collection,
        embedder=embedder,
    )
    app.state.retriever = Retriever(
        store=app.state.memory_store,
        search_limit=settings.rag_search_limit,
        context_limit=settings.rag_context_limit,
        score_threshold=settings.rag_score_threshold,
    )
    yield


app = FastAPI(title="PAItryk", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_frontend_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(admin_chat_router, prefix="/api")
app.include_router(admin_ingest_router, prefix="/api")
app.include_router(models_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    chat_model = (
        settings.anthropic_model
        if settings.chat_provider == "claude"
        else settings.ollama_chat_model
    )
    ingest_model = (
        settings.anthropic_model
        if settings.ingest_provider == "claude"
        else settings.ollama_ingest_model
    )
    return {
        "ok": True,
        "chat": {
            "provider": settings.chat_provider,
            "model": chat_model,
        },
        "ingest": {
            "provider": settings.ingest_provider,
            "model": ingest_model,
        },
        "rag": {
            "embeddings": {
                "provider": "ollama",
                "model": settings.ollama_embed_model,
            },
            "reranker": {
                "provider": "ollama",
                "model": settings.ollama_reranker_model,
            },
            "qdrant_collection": settings.qdrant_collection,
        },
    }
