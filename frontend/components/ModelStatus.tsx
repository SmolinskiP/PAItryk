"use client";

import { Activity, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { getHealth, getOllamaModels, HealthResponse, OllamaModelsResponse } from "@/lib/api";

export function ModelStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ollama, setOllama] = useState<OllamaModelsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const [healthResponse, ollamaResponse] = await Promise.all([getHealth(), getOllamaModels()]);
      setHealth(healthResponse);
      setOllama(ollamaResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się sprawdzić modeli");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  const missing = ollama ? Object.entries(ollama.missing) : [];

  return (
    <section className="panel">
      <div className="panel-header">
        <div className="panel-title">
          <strong>Model status</strong>
          <span>{ollama?.host ?? "sprawdzam Ollamę"}</span>
        </div>
        <button className="btn icon-btn" disabled={loading} onClick={() => void reload()}>
          <RefreshCw size={16} />
        </button>
      </div>
      <div className="side-scroll">
        {error ? <div className="error">{error}</div> : null}
        {health ? (
          <div className="memory-list">
            <StatusRow label="chat" provider={health.chat.provider} model={health.chat.model} />
            <StatusRow
              label="ingest"
              provider={health.ingest.provider}
              model={health.ingest.model}
            />
            <StatusRow
              label="embeddings"
              provider={health.rag.embeddings.provider}
              model={health.rag.embeddings.model}
            />
            <StatusRow
              label="reranker"
              provider={health.rag.reranker.provider}
              model={health.rag.reranker.model}
            />
            <div className="memory-row">
              <header>
                <div className="meta">
                  <span className={missing.length ? "pill danger" : "pill ok"}>
                    {missing.length ? "missing" : "ollama ok"}
                  </span>
                  <span className="pill">{ollama?.models.length ?? 0} modeli</span>
                </div>
              </header>
              {missing.length ? (
                <p>{missing.map(([role, model]) => `${role}: ${model}`).join("\n")}</p>
              ) : (
                <p>Wszystkie skonfigurowane modele Ollamy są dostępne lokalnie.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="empty">Ładowanie statusu modeli.</div>
        )}
      </div>
    </section>
  );
}

function StatusRow({
  label,
  provider,
  model
}: {
  label: string;
  provider: string;
  model: string;
}) {
  return (
    <article className="memory-row">
      <header>
        <div className="meta">
          <span className="pill ok">
            <Activity size={13} />
            {label}
          </span>
          <span className="pill">{provider}</span>
        </div>
      </header>
      <p>{model}</p>
    </article>
  );
}
