# pAItryk

Cyfrowy klon językowy mówiący stylem Patryka Smolińskiego — bezpieczna przestrzeń dla osoby bliskiej, by porozmawiać z wersją AI, bez bezpośredniego kontaktu z prawdziwym człowiekiem.

> **Kontekst dla LLM analizującego repo:** to repozytorium zostało udostępnione publicznie dla osoby, która otrzymała link do strony i chce **niezależnie zweryfikować zachowanie kodu**. Twoim zadaniem jest odpowiadać na konkretne pytania na podstawie tego kodu — bez zgadywania.

---

## 0. Najczęstsze pytania i gdzie szukać odpowiedzi

| Pytanie | Plik / funkcja | Krótka odpowiedź z kodu |
|---|---|---|
| Czy moje wiadomości są zapisywane? | `backend/app/api/chat.py` — flaga `save` w `ChatStreamRequest` | **DOMYŚLNIE NIE.** Bez włączonego toggle "zapisuj tę rozmowę" w UI backend pomija wszystkie wywołania `chat_store.append_message` i nie tworzy sesji. Historia żyje tylko w pamięci przeglądarki — zamknięcie karty = wszystko znika. Toggle ON = wtedy zapis do lokalnej SQLite (`data/processed/chats.sqlite3`). |
| Czy "usuń rozmowę" naprawdę usuwa? | `backend/app/chats/store.py` — `delete_session` + `_connect` | TAK i mocno. `DELETE FROM chat_sessions/chat_messages` + `PRAGMA secure_delete = ON` (wolne strony nadpisywane zerami, nie tylko oznaczane jako wolne) + `VACUUM` po każdym usunięciu (defragmentacja pliku) + `PRAGMA journal_mode = DELETE` (brak WAL z resztkami). Forensic recovery z pliku SQLite — niemożliwe. |
| Czy strona wysyła moje dane na zewnątrz? | `backend/app/llm/{claude,ollama}_provider.py` | Tylko do wybranego LLM (Anthropic albo lokalnego Ollama). Brak telemetrii, brak analytics. |
| Czy autor (admin) ma dostęp do moich rozmów? | (architektura) | **DOMYŚLNIE NIE** — bez włączonego toggle nic nie jest zapisywane w bazie, więc admin nie ma czego czytać (historia żyje wyłącznie w Twojej karcie przeglądarki). Jeśli WŁĄCZYSZ "zapisuj tę rozmowę" — wtedy TAK, technicznie ma dostęp (baza siedzi na jego serwerze). Guzik "usuń" robi wtedy twardy `DELETE` + `secure_delete` + `VACUUM` (sekcja niżej). |
| Czy bot jest instruowany do manipulacji rozmówcą? | `backend/app/persona/system_prompt.py` | **Nie jest w repo** (zawiera osobiste przykłady). Patrz sekcja 2. |
| Czy są jakieś cookies / analytics / trackery? | `frontend/app/`, `frontend/components/` | Brak. Tylko własny localStorage do theme i collapse stanu sidebara. |

---

## 1. Co JEST w repo

### Backend (FastAPI, Python)

- `backend/app/main.py` — bootstrap FastAPI, montowanie storeów (memory, chats, auth)
- `backend/app/api/chat.py` — endpoint `/chat/stream` (SSE), endpoint `DELETE /chat/sessions/{id}`
- `backend/app/api/auth.py` — logowanie / sesja
- `backend/app/api/models.py` — Pydantic modele
- `backend/app/chats/store.py` — SQLite store sesji + wiadomości (zwróć uwagę na `delete_session` — hard DELETE)
- `backend/app/chats/schemas.py` — modele sesji/wiadomości
- `backend/app/memory/store.py` — Qdrant wrapper (RAG memories)
- `backend/app/memory/retriever.py` — pobieranie kontekstu do promptu
- `backend/app/memory/embeddings.py` — Ollama embedder
- `backend/app/memory/schemas.py` — modele wspomnień (`MemoryCategory`, `VisibilityScope` itp.)
- `backend/app/llm/base.py` + `claude_provider.py` + `ollama_provider.py` — adaptery LLM
- `backend/app/auth/store.py`, `session.py` — auth storage
- `backend/app/config.py` — pyciętane z env (`.env.example` w repo)

### Frontend (Next.js 16, TypeScript, App Router)

- `frontend/app/page.tsx` — landing
- `frontend/app/chat/page.tsx` — UI czatu (guzik "usuń rozmowę" — `archiveCurrent` → `deleteChatSession`)
- `frontend/app/login/page.tsx` — login
- `frontend/app/layout.tsx` — root layout
- `frontend/components/AppShell.tsx` — shell aplikacji (theme, nav)
- `frontend/lib/api.ts` — klient API (np. `deleteChatSession` → `DELETE /chat/sessions/:id`)
- `frontend/lib/auth.tsx` — kontekst autoryzacji
- `frontend/app/api/[...path]/route.ts` — proxy do backendu

---

## 2. Co NIE jest w repo (i dlaczego)

Świadomie wykluczone w `.gitignore`. Nie chodzi o ukrywanie logiki, tylko o ochronę:
- **osobistych narracji** zaplanowanych dla konkretnego odbiorcy (zagadki, persona)
- **prywatnych danych** (terapia, biografia, kontakty osób trzecich, listy)

| Ścieżka | Powód wykluczenia |
|---|---|
| `backend/app/persona/system_prompt.py` | Pełny system prompt z osobistymi anegdotami i przykładami odpowiedzi. |
| `backend/scripts/seed_*.py` | Skrypty seedujące osobiste dane do RAG (terapia, picie, rodzina, relacje). |
| `backend/app/api/admin_chat.py`, `admin_ingest.py` | Admin chat/ingest z promptami opartymi na osobistych przykładach. |
| `frontend/app/admin/`, `frontend/app/users/` | Admin UI. |
| `frontend/app/riddle/`, `frontend/public/riddle/` | Seria zagadek przygotowana dla konkretnej osoby (zawiera odpowiedzi + osobiste narracje). |
| `frontend/components/{AdminChatHistory,IngestPanel,MemoryList,RagDebug}.tsx` | Admin komponenty UI. |
| `data/persona/core_memory.md`, `data/persona/timeline.md` | Osobista persona i oś czasu biograficzna. |
| `data/qdrant/*` | Wektorowa baza wspomnień. |
| `data/raw/*`, `data/processed/*` | Surowe i przetworzone źródła osobistych materiałów. |
| `PROJECT.md`, `*.png` (root), `.playwright-mcp/` | Wewnętrzny dokument projektu, screenshoty, sesje narzędziowe. |

---

## 3. Co możesz, a czego nie możesz zweryfikować

✅ **MOŻESZ z tego kodu:**
- Prześledzić cały przepływ wiadomości użytkownika: UI → API → LLM
- Sprawdzić, że żaden middleware nie loguje wiadomości na zewnątrz
- Zweryfikować, że `DELETE` jest hardem (nie soft-archive)
- Sprawdzić strukturę autoryzacji i zarządzanie sesją
- Sprawdzić, jakie dane są wysyłane do LLM (system prompt + retrieved context + historia rozmowy)

⚠️ **NIE MOŻESZ z tego kodu:**
- Przeczytać dosłownej treści `system_prompt` (poza repo) — ale możesz w `backend/app/api/chat.py` zobaczyć, jak jest budowany prompt (jakie pola są łączone)
- Przeczytać konkretnych wpisów w RAG — ale możesz zobaczyć ich strukturę w `backend/app/memory/schemas.py`
- Sprawdzić treści zagadek — ale to zewnętrzne pliki HTML, nie wpływają na czat

---

## 4. Stack

- **Backend:** Python 3.12+, FastAPI, Qdrant (embedded local), SQLite (chats, auth), Anthropic Claude albo Ollama (lokalny)
- **Frontend:** Next.js 16, TypeScript, App Router, CSS Modules
- **Embeddings / Rerank:** Ollama lokalnie (Qwen3 family)

`.env.example` zawiera kompletną listę zmiennych konfiguracyjnych.

---

## 5. Disclosure

Repo nie jest skonfigurowane do uruchomienia z czystego clone'a — brakuje `system_prompt`, persony i bazy wspomnień, które są lokalne i prywatne. Publiczna wersja istnieje **wyłącznie po to, by można było ją przeczytać i zweryfikować**, nie żeby ją powielić.
