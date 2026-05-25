export type Role = "user" | "assistant";
export type UserRole = "user" | "admin";

export type AuthUser = {
  username: string;
  role: UserRole;
};

export type PublicUser = AuthUser & {
  label: string;
};

export type AuthResponse = {
  user: AuthUser;
};

export type UsersResponse = {
  users: PublicUser[];
};

export type ChatMessage = {
  role: Role;
  content: string;
};

export type MemoryCategory =
  | "core"
  | "episodic"
  | "semantic"
  | "relation"
  | "style"
  | "boundary"
  | "project";

export type VisibilityScope = "public" | "private" | "per_relation";

export type MemorySource = {
  kind: string;
  ref?: string | null;
  quote?: string | null;
};

export type MemoryRecord = {
  id: string;
  schema_version: number;
  content: string;
  category: MemoryCategory;
  tags: string[];
  visibility: VisibilityScope;
  relations: string[];
  source: MemorySource;
  confidence: number;
  created_at: string;
  updated_at: string;
};

export type RetrievedMemory = {
  memory: MemoryRecord;
  vector_score: number;
  rerank_score?: number | null;
};

export type ChatResponse = {
  message: ChatMessage;
  provider: string;
  session_id: string;
  retrieved_memories: RetrievedMemory[];
};

export type ChatSession = {
  id: string;
  audience: "public" | "admin";
  title: string;
  archived: boolean;
  created_at: string;
  updated_at: string;
};

export type ChatSessionWithMessages = ChatSession & {
  messages: ChatMessage[];
};

export type ChatSessionsResponse = {
  sessions: ChatSession[];
};

export type ChatHistoryResponse = {
  session: ChatSessionWithMessages;
};

export type AdminChatResponse = {
  message: ChatMessage;
  provider: string;
  created_memories: MemoryRecord[];
  retrieved_memories: RetrievedMemory[];
};

export type MemoryListResponse = {
  memories: MemoryRecord[];
  next_offset?: string | null;
};

export type HealthResponse = {
  ok: boolean;
  chat: {
    provider: string;
    model: string;
  };
  ingest: {
    provider: string;
    model: string;
  };
  rag: {
    embeddings: {
      provider: string;
      model: string;
    };
    reranker: {
      provider: string;
      model: string;
    };
    qdrant_collection: string;
  };
};

export type OllamaModelsResponse = {
  host: string;
  models: string[];
  configured: Record<string, string>;
  missing: Record<string, string>;
};

export type MemoryCreate = {
  content: string;
  category: MemoryCategory;
  tags: string[];
  visibility: VisibilityScope;
  relations: string[];
  source: MemorySource;
  confidence: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export async function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

export async function getCurrentUser(): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/me");
}

export async function listUsers(): Promise<UsersResponse> {
  return request<UsersResponse>("/auth/users");
}

export async function createUser(input: {
  username: string;
  password: string;
  role: UserRole;
}): Promise<PublicUser> {
  return request<PublicUser>("/auth/users", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function updateUserRole(username: string, role: UserRole): Promise<PublicUser> {
  return request<PublicUser>(`/auth/users/${encodeURIComponent(username)}/role`, {
    method: "PATCH",
    body: JSON.stringify({ role })
  });
}

export async function resetUserPassword(username: string, password: string): Promise<PublicUser> {
  return request<PublicUser>(`/auth/users/${encodeURIComponent(username)}/password`, {
    method: "POST",
    body: JSON.stringify({ password })
  });
}

export async function deleteUser(username: string): Promise<void> {
  return request<void>(`/auth/users/${encodeURIComponent(username)}`, { method: "DELETE" });
}

export async function sendChat(
  messages: ChatMessage[],
  recipient: string | null
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ messages, recipient })
  });
}

export async function streamChat(
  input: {
    message: string;
    recipient: string | null;
    session_id: string | null;
  },
  handlers: {
    onMeta?: (meta: { session_id: string; provider: string }) => void;
    onThinking?: (content: string) => void;
    onDelta: (content: string) => void;
    onDone?: (data: { session_id: string }) => void;
    onError?: (message: string) => void;
  }
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });

  if (!response.ok || !response.body) {
    throw new Error((await response.text()) || `${response.status} ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const eventText of events) {
      const parsed = parseSse(eventText);
      if (!parsed) {
        continue;
      }
      if (parsed.event === "meta") {
        handlers.onMeta?.(parsed.data as { session_id: string; provider: string });
      } else if (parsed.event === "thinking") {
        handlers.onThinking?.((parsed.data as { content: string }).content);
      } else if (parsed.event === "delta") {
        handlers.onDelta((parsed.data as { content: string }).content);
      } else if (parsed.event === "done") {
        handlers.onDone?.(parsed.data as { session_id: string });
      } else if (parsed.event === "error") {
        handlers.onError?.((parsed.data as { message: string }).message);
      }
    }
  }
}

function parseSse(raw: string): { event: string; data: unknown } | null {
  const event = raw
    .split("\n")
    .find((line) => line.startsWith("event: "))
    ?.slice(7);
  const data = raw
    .split("\n")
    .find((line) => line.startsWith("data: "))
    ?.slice(6);
  if (!event || !data) {
    return null;
  }
  return { event, data: JSON.parse(data) };
}

export async function listChatSessions(): Promise<ChatSessionsResponse> {
  return request<ChatSessionsResponse>("/chat/sessions");
}

export async function getChatSession(id: string): Promise<ChatHistoryResponse> {
  return request<ChatHistoryResponse>(`/chat/sessions/${id}`);
}

export async function deleteChatSession(id: string): Promise<void> {
  return request<void>(`/chat/sessions/${id}`, { method: "DELETE" });
}

export async function sendAdminChat(
  messages: ChatMessage[],
  autoWrite: boolean
): Promise<AdminChatResponse> {
  return request<AdminChatResponse>("/admin/chat", {
    method: "POST",
    body: JSON.stringify({ messages, auto_write: autoWrite })
  });
}

export async function streamAdminChat(
  messages: ChatMessage[],
  autoWrite: boolean,
  handlers: {
    onMeta?: (meta: {
      provider: string;
      created_memories: MemoryRecord[];
      retrieved_memories: RetrievedMemory[];
    }) => void;
    onThinking?: (content: string) => void;
    onDelta: (content: string) => void;
    onDone?: () => void;
    onError?: (message: string) => void;
  }
): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, auto_write: autoWrite })
  });

  if (!response.ok || !response.body) {
    throw new Error((await response.text()) || `${response.status} ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const eventText of events) {
      const parsed = parseSse(eventText);
      if (!parsed) {
        continue;
      }
      if (parsed.event === "meta") {
        handlers.onMeta?.(
          parsed.data as {
            provider: string;
            created_memories: MemoryRecord[];
            retrieved_memories: RetrievedMemory[];
          }
        );
      } else if (parsed.event === "thinking") {
        handlers.onThinking?.((parsed.data as { content: string }).content);
      } else if (parsed.event === "delta") {
        handlers.onDelta((parsed.data as { content: string }).content);
      } else if (parsed.event === "done") {
        handlers.onDone?.();
      } else if (parsed.event === "error") {
        handlers.onError?.((parsed.data as { message: string }).message);
      }
    }
  }
}

export async function listMemories(): Promise<MemoryListResponse> {
  return request<MemoryListResponse>("/admin/memories");
}

export type IngestUploadResponse = {
  paths: string[];
};

export async function uploadIngestFiles(files: File[]): Promise<IngestUploadResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const response = await fetch(`${API_BASE}/admin/ingest/upload`, {
    method: "POST",
    credentials: "include",
    body: form
  });
  if (!response.ok) {
    throw new Error((await response.text()) || `${response.status}`);
  }
  return (await response.json()) as IngestUploadResponse;
}

export type IngestStartEvent = {
  provider: string;
  files: string[];
  dry_run: boolean;
};

export type IngestFileStartEvent = {
  file: string;
  source_kind: string;
  chunks_total: number;
};

export type IngestChunkEvent = {
  file: string;
  label: string;
  chars: number;
  memories: number;
  samples: { category: string; visibility: string; content: string }[];
};

export type IngestFileDoneEvent = {
  file: string;
  total: number;
};

export async function streamIngest(
  paths: string[],
  handlers: {
    onStart?: (event: IngestStartEvent) => void;
    onFileStart?: (event: IngestFileStartEvent) => void;
    onChunkDone?: (event: IngestChunkEvent) => void;
    onChunkError?: (event: { file: string; label: string; message: string }) => void;
    onFileDone?: (event: IngestFileDoneEvent) => void;
    onDone?: (event: { grand_total: number }) => void;
    onError?: (message: string) => void;
  },
  options: { dryRun?: boolean; provider?: "claude" | "ollama" } = {}
): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/ingest/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      paths,
      dry_run: options.dryRun ?? false,
      provider: options.provider ?? null
    })
  });

  if (!response.ok || !response.body) {
    throw new Error((await response.text()) || `${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const eventText of events) {
      const parsed = parseSse(eventText);
      if (!parsed) continue;
      switch (parsed.event) {
        case "start":
          handlers.onStart?.(parsed.data as IngestStartEvent);
          break;
        case "file_start":
          handlers.onFileStart?.(parsed.data as IngestFileStartEvent);
          break;
        case "chunk_done":
          handlers.onChunkDone?.(parsed.data as IngestChunkEvent);
          break;
        case "chunk_error":
          handlers.onChunkError?.(
            parsed.data as { file: string; label: string; message: string }
          );
          break;
        case "file_done":
          handlers.onFileDone?.(parsed.data as IngestFileDoneEvent);
          break;
        case "done":
          handlers.onDone?.(parsed.data as { grand_total: number });
          break;
        case "error":
          handlers.onError?.((parsed.data as { message: string }).message);
          break;
      }
    }
  }
}

export async function createMemory(memory: MemoryCreate): Promise<MemoryRecord> {
  return request<MemoryRecord>("/admin/memories", {
    method: "POST",
    body: JSON.stringify(memory)
  });
}

export async function updateMemory(
  id: string,
  patch: Partial<Omit<MemoryCreate, "source">>
): Promise<MemoryRecord> {
  return request<MemoryRecord>(`/admin/memories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch)
  });
}

export async function deleteMemory(id: string): Promise<void> {
  return request<void>(`/admin/memories/${id}`, { method: "DELETE" });
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function getOllamaModels(): Promise<OllamaModelsResponse> {
  return request<OllamaModelsResponse>("/models/ollama");
}

export async function listAdminChatSessions(
  includeArchived = true
): Promise<ChatSessionsResponse> {
  return request<ChatSessionsResponse>(
    `/admin/chat-sessions?include_archived=${String(includeArchived)}`
  );
}

export async function getAdminChatSession(id: string): Promise<ChatHistoryResponse> {
  return request<ChatHistoryResponse>(`/admin/chat-sessions/${id}`);
}

export async function restoreChatSession(id: string): Promise<void> {
  return request<void>(`/admin/chat-sessions/${id}/restore`, { method: "POST" });
}
