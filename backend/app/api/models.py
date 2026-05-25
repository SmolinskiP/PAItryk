import httpx
from fastapi import APIRouter, Depends

from app.auth.session import require_admin
from app.config import settings

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/models/ollama")
async def ollama_models() -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{settings.ollama_host}/api/tags")
        response.raise_for_status()
    payload = response.json()
    models = sorted(model["name"] for model in payload.get("models", []) if "name" in model)
    configured = {
        "chat": settings.ollama_chat_model,
        "embeddings": settings.ollama_embed_model,
        "reranker": settings.ollama_reranker_model,
    }
    if settings.ingest_provider == "ollama":
        configured["ingest"] = settings.ollama_ingest_model
    available = set(models)
    return {
        "host": settings.ollama_host,
        "models": models,
        "configured": configured,
        "missing": {
            role: model for role, model in configured.items() if model not in available
        },
    }
