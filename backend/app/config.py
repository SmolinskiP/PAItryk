from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        extra="ignore",
        case_sensitive=False,
    )

    chat_provider: Literal["claude", "ollama", "openai"]
    ingest_provider: Literal["claude", "ollama", "openai"]

    anthropic_api_key: str = ""
    anthropic_model: str
    anthropic_thinking_budget: int = 0

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    ollama_host: str
    ollama_chat_model: str
    ollama_ingest_model: str
    ollama_embed_model: str
    ollama_reranker_model: str

    qdrant_path: str
    qdrant_collection: str
    chat_db_path: str
    auth_db_path: str = "data/processed/auth.sqlite3"
    rag_search_limit: int
    rag_context_limit: int
    rag_score_threshold: float

    backend_host: str
    backend_port: int
    frontend_origin: str
    frontend_origins: str

    session_secret: str = "change-me"
    session_cookie_secure: bool = False

    log_level: str

    @field_validator("qdrant_path", "chat_db_path", "auth_db_path")
    @classmethod
    def resolve_project_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str(ROOT / path)


settings = Settings()


def get_frontend_origins() -> list[str]:
    origins = [origin.strip() for origin in settings.frontend_origins.split(",")]
    if settings.frontend_origin:
        origins.append(settings.frontend_origin)
    return sorted({origin for origin in origins if origin})
