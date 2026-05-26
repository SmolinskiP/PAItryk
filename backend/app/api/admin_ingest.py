"""Ingest pipeline z plików (docs/, data/raw/) do RAG.

Endpoint streamingowy — emituje progress per chunk, więc CLI / UI mogą pokazać postęp.
Wykorzystuje istniejący ekstraktor z admin_chat (`EXTRACTION_SYSTEM`,
`_parse_memory_creates`) — ten sam prompt co w admin chacie, tylko zasilany
fragmentami dokumentu zamiast wiadomością Patryka.
"""

import json
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.admin_chat import _extraction_system, _parse_memory_creates
from app.auth.session import require_admin
from app.config import ROOT, settings
from app.llm.base import ChatMessage, LLMProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.ollama_provider import OllamaProvider

router = APIRouter(dependencies=[Depends(require_admin)])


class UploadResponse(BaseModel):
    paths: list[str]


@router.post("/admin/ingest/upload", response_model=UploadResponse)
async def upload_files(files: Annotated[list[UploadFile], File(...)]) -> UploadResponse:
    target_dir = ROOT / "data" / "raw"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name
        if not safe_name:
            continue
        dest = target_dir / safe_name
        body = await upload.read()
        dest.write_bytes(body)
        saved.append(f"data/raw/{safe_name}")

    if not saved:
        raise HTTPException(status_code=400, detail="Brak plików do zapisania")
    return UploadResponse(paths=saved)


class IngestRequest(BaseModel):
    paths: list[str] = Field(
        default_factory=list,
        description="Ścieżki plików (relatywne do ROOT projektu lub absolutne). Pusty = docs/*",
    )
    provider: str | None = Field(
        default=None, description="claude lub ollama; default = settings.ingest_provider"
    )
    dry_run: bool = Field(default=False, description="Tylko podgląd, bez zapisu do Qdrant")


def _resolve_paths(raw: list[str]) -> list[Path]:
    if not raw:
        docs = ROOT / "docs"
        if not docs.exists():
            return []
        return sorted(p for p in docs.iterdir() if p.is_file())
    out: list[Path] = []
    for r in raw:
        p = Path(r)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file():
            out.append(p)
    return out


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Po sekcjach `## `; intro = wszystko przed pierwszą sekcją."""
    chunks: list[tuple[str, str]] = []
    label = "intro"
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            body = "\n".join(buf).strip()
            if body:
                chunks.append((label, body))
            label = line.lstrip("# ").strip()
            buf = [line]
        else:
            buf.append(line)
    body = "\n".join(buf).strip()
    if body:
        chunks.append((label, body))
    return chunks


def _chunk_paragraphs(text: str, group: int = 4) -> list[tuple[str, str]]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out: list[tuple[str, str]] = []
    for i in range(0, len(paragraphs), group):
        body = "\n\n".join(paragraphs[i : i + group])
        out.append((f"frag-{i // group + 1}", body))
    return out


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx(path)
    return path.read_text(encoding="utf-8")


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as docx:
            xml = docx.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Nie udało się odczytać DOCX: {path.name}") from exc

    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [
            text.text or ""
            for text in paragraph.findall(".//w:t", namespace)
            if text.text is not None
        ]
        body = "".join(parts).strip()
        if body:
            paragraphs.append(body)
    return "\n\n".join(paragraphs)


def _detect_source_kind(name: str) -> str:
    n = name.lower()
    if "terapia" in n or "therapy" in n:
        return "therapy_note"
    if "mail" in n or "email" in n:
        return "email"
    if "pochwala" in n:
        return "official_letter"
    return "doc"


def _make_provider(name: str | None) -> LLMProvider:
    chosen = name or settings.ingest_provider
    if chosen == "claude":
        return ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    return OllamaProvider(host=settings.ollama_host, model=settings.ollama_ingest_model)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/admin/ingest/stream")
async def ingest_stream(req: IngestRequest, request: Request) -> StreamingResponse:
    paths = _resolve_paths(req.paths)
    if not paths:
        raise HTTPException(status_code=400, detail="Brak plików do ingestu")

    provider = _make_provider(req.provider)
    store = request.app.state.memory_store

    async def events() -> AsyncIterator[str]:
        yield _sse(
            "start",
            {
                "provider": provider.name,
                "files": [p.name for p in paths],
                "dry_run": req.dry_run,
            },
        )

        grand_total = 0
        try:
            for path in paths:
                text = _read_text(path)
                chunks = (
                    _chunk_markdown(text)
                    if path.suffix.lower() in {".md", ".markdown"}
                    else _chunk_paragraphs(text)
                )
                source_kind = _detect_source_kind(path.name)

                yield _sse(
                    "file_start",
                    {
                        "file": path.name,
                        "source_kind": source_kind,
                        "chunks_total": len(chunks),
                    },
                )

                file_total = 0
                for label, body in chunks:
                    try:
                        raw = await provider.chat(
                            [ChatMessage(role="user", content=body)],
                            _extraction_system(),
                        )
                    except Exception as exc:
                        yield _sse(
                            "chunk_error",
                            {"file": path.name, "label": label, "message": str(exc)},
                        )
                        continue

                    memories = _parse_memory_creates(
                        raw,
                        source_ref=f"{path.name}#{label}",
                        source_kind=source_kind,
                    )
                    if memories and not req.dry_run:
                        await store.add_many(memories)
                    file_total += len(memories)

                    yield _sse(
                        "chunk_done",
                        {
                            "file": path.name,
                            "label": label,
                            "chars": len(body),
                            "memories": len(memories),
                            "samples": [
                                {
                                    "category": m.category.value,
                                    "visibility": m.visibility.value,
                                    "content": m.content[:120],
                                }
                                for m in memories[:3]
                            ],
                        },
                    )

                grand_total += file_total
                yield _sse("file_done", {"file": path.name, "total": file_total})

            yield _sse("done", {"grand_total": grand_total})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")
