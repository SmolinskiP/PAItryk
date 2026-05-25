"use client";

import {
  Archive,
  ChevronDown,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Send,
  Sparkles
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  deleteChatSession,
  ChatMessage,
  ChatSession,
  getChatSession,
  listChatSessions,
  streamChat
} from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";

import styles from "./page.module.css";

type ChatMsg = ChatMessage & { thinking?: string };

const SUGGESTED_PROMPTS = [
  "Dlaczego mi to robiłeś, skoro wiedziałeś że mnie to boli?",
  "Czy naprawdę się zmieniłeś, czy to kolejna wersja tej samej historii?",
  "Jakieś konkretne, dobre sytuacje które pamiętasz z naszego czasu razem?",
  "Jak teraz wygląda twoje życie — co się przez te lata zmieniło?",
  "Gdybyś mógł cofnąć się do konkretnego momentu, co byś zrobił inaczej?",
  "Czego tak naprawdę ode mnie chcesz — po co mi to wysłałeś?",
];

const SIDEBAR_KEY = "paitryk-sidebar-collapsed";
const RECIPIENT = "karolina";
const USER_INITIAL = "?";

export default function ChatPage() {
  return (
    <ProtectedRoute roles={["user", "admin"]}>
      <ChatExperience />
    </ProtectedRoute>
  );
}

function ChatExperience() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [overlayReady, setOverlayReady] = useState(false);
  const [saveHistory, setSaveHistory] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const isMobile = window.matchMedia("(max-width: 640px)").matches;
    const saved = window.localStorage.getItem(SIDEBAR_KEY);
    setSidebarCollapsed(isMobile ? true : saved === "1");
    void reloadSessions();
  }, []);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  }, [input]);

  useEffect(() => {
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: "smooth"
    });
  }, [messages]);

  async function reloadSessions() {
    try {
      const response = await listChatSessions();
      setSessions(response.sessions);
    } catch {
      // ignore — error already shown elsewhere if relevant
    }
  }

  async function openSession(id: string) {
    setError(null);
    if (window.matchMedia("(max-width: 640px)").matches) setSidebarCollapsed(true);
    try {
      const response = await getChatSession(id);
      setSessionId(response.session.id);
      setMessages(response.session.messages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się otworzyć rozmowy");
    }
  }

  function newSession() {
    setSessionId(null);
    setMessages([]);
    setInput("");
    setError(null);
    textareaRef.current?.focus();
  }

  async function deleteCurrent(id: string) {
    await deleteChatSession(id);
    if (sessionId === id) newSession();
    await reloadSessions();
  }

  useEffect(() => {
    if (!sidebarCollapsed) {
      const t = setTimeout(() => setOverlayReady(true), 350);
      return () => clearTimeout(t);
    } else {
      setOverlayReady(false);
    }
  }, [sidebarCollapsed]);

  function toggleSidebar() {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      return next;
    });
  }

  async function submit(content?: string) {
    const text = (content ?? input).trim();
    if (!text || loading) return;

    const userMessage: ChatMsg = { role: "user", content: text };
    const assistantMessage: ChatMsg = { role: "assistant", content: "" };
    setMessages((current) => [...current, userMessage, assistantMessage]);
    setInput("");
    setLoading(true);
    setError(null);

    let activeSessionId = sessionId;
    const historyForRequest: ChatMessage[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: "user", content: text }
    ];
    try {
      await streamChat(
        {
          messages: historyForRequest,
          recipient: RECIPIENT,
          session_id: activeSessionId,
          save: saveHistory
        },
        {
          onMeta: (meta) => {
            activeSessionId = meta.session_id;
            setSessionId(meta.session_id);
          },
          onThinking: (delta) => {
            setMessages((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              next[next.length - 1] = {
                ...last,
                thinking: (last.thinking ?? "") + delta
              };
              return next;
            });
          },
          onDelta: (delta) => {
            setMessages((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + delta };
              return next;
            });
          },
          onError: (message) => setError(message)
        }
      );
      if (saveHistory) await reloadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd rozmowy");
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  const isEmpty = messages.length === 0;
  const sidebarClass = `${styles.sidebar} ${sidebarCollapsed ? styles.collapsed : ""}`;

  return (
    <div className={styles.layout}>
      <aside className={sidebarClass}>
        <div className={styles.sidebarHeader}>
          <button
            className={styles.toggle}
            onClick={toggleSidebar}
            title={sidebarCollapsed ? "Rozwiń pasek" : "Zwiń pasek"}
            aria-label={sidebarCollapsed ? "Rozwiń pasek" : "Zwiń pasek"}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <span className={styles.sidebarTitle}>Rozmowy</span>
        </div>

        <button className={styles.newChat} onClick={newSession} title="Nowa rozmowa">
          <MessageSquarePlus size={17} />
          <span>Nowa rozmowa</span>
        </button>

        <div className={styles.sessionList}>
          {sessions.length === 0 ? (
            <p className={styles.empty}>Brak zapisanych rozmów.</p>
          ) : null}
          {sessions.map((session) => (
            <div className={styles.sessionWrap} key={session.id}>
              <button
                className={`${styles.session} ${
                  session.id === sessionId ? styles.sessionActive : ""
                }`}
                onClick={() => void openSession(session.id)}
                title={session.title}
              >
                <span className={styles.sessionDot} />
                <span className={styles.sessionMeta}>
                  <strong>{session.title}</strong>
                  <em>
                    {new Date(session.updated_at).toLocaleDateString("pl-PL", {
                      day: "numeric",
                      month: "short"
                    })}
                  </em>
                </span>
              </button>
              <button
                className={styles.sessionArchive}
                onClick={() => void deleteCurrent(session.id)}
                title="Usuń rozmowę"
                aria-label="Usuń rozmowę"
              >
                <Archive size={14} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className={styles.main}>
        {!sidebarCollapsed ? (
          <div
            className={styles.sidebarOverlay}
            onClick={overlayReady ? toggleSidebar : undefined}
            aria-hidden
          />
        ) : null}
        {sidebarCollapsed ? (
          <button
            className={styles.mobileMenuBtn}
            onClick={toggleSidebar}
            aria-label="Otwórz listę rozmów"
          >
            <PanelLeftOpen size={18} />
          </button>
        ) : null}
        {isEmpty ? (
          <EmptyHero onPick={(text) => void submit(text)} disabled={loading} />
        ) : (
          <div className={styles.messages} ref={messagesRef}>
            {messages.map((message, index) => (
              <Bubble
                key={index}
                message={message}
                loading={loading}
                isLast={index === messages.length - 1}
              />
            ))}
            {error ? <div className={styles.error}>{error}</div> : null}
          </div>
        )}

        <div className={styles.composerWrap}>
          <div className={styles.composer}>
            <textarea
              ref={textareaRef}
              className={styles.textarea}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Napisz wiadomość..."
              rows={1}
            />
            <button
              className={styles.sendBtn}
              disabled={loading || !input.trim()}
              onClick={() => void submit()}
              title="Wyślij (Enter)"
              aria-label="Wyślij wiadomość"
            >
              {loading ? <Spinner /> : <Send size={18} strokeWidth={2.4} />}
            </button>
          </div>
          <div className={styles.composerHint}>
            <label className={styles.saveToggle}>
              <input
                type="checkbox"
                checked={saveHistory}
                onChange={(event) => setSaveHistory(event.target.checked)}
              />
              <span>zapisuj tę rozmowę</span>
            </label>
            <span>·</span>
            <kbd>Enter</kbd> wyślij <span>·</span> <kbd>Shift</kbd>+<kbd>Enter</kbd> nowa linia
          </div>
        </div>
      </main>
    </div>
  );
}

function EmptyHero({
  onPick,
  disabled
}: {
  onPick: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <div className={styles.emptyHero}>
      <div className={styles.heroAvatar} aria-hidden>
        <span>P</span>
      </div>
      <h1 className={styles.heroHeadline}>
        Cześć.
        <br />
        <span className={styles.heroAccent}>O czym chcesz pogadać?</span>
      </h1>
<div className={styles.suggestions}>
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            className={styles.suggestion}
            disabled={disabled}
            onClick={() => onPick(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function Bubble({
  message,
  loading,
  isLast
}: {
  message: ChatMsg;
  loading: boolean;
  isLast: boolean;
}) {
  const isUser = message.role === "user";
  const isStreamingThis = !isUser && loading && isLast;
  const isThinkingActive = isStreamingThis && !message.content;
  const hasThinking = !isUser && Boolean(message.thinking);
  const showSpinnerOnly = isThinkingActive && !hasThinking;

  return (
    <div className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleBot}`}>
      <div className={styles.bubbleAvatar} aria-hidden>
        {isUser ? USER_INITIAL : "P"}
      </div>
      <div className={styles.bubbleStack}>
        {hasThinking ? (
          <ThinkingWidget text={message.thinking!} active={isThinkingActive} />
        ) : null}
        {message.content || !isStreamingThis ? (
          <div className={styles.bubbleContent}>
            {message.content || (showSpinnerOnly ? <Spinner large /> : "")}
          </div>
        ) : showSpinnerOnly ? (
          <div className={styles.bubbleContent}>
            <Spinner large />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ThinkingWidget({ text, active }: { text: string; active: boolean }) {
  const preRef = useRef<HTMLPreElement | null>(null);
  useEffect(() => {
    if (active && preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
  }, [text, active]);

  return (
    <details className={`${styles.thinkingBox} ${active ? styles.thinkingActive : ""}`}>
      <summary className={styles.thinkingSummary}>
        {active ? <Spinner /> : <Sparkles size={13} />}
        <span>{active ? "myślę..." : "tok myślenia"}</span>
        <ChevronDown size={13} className={styles.thinkingChevron} />
      </summary>
      <pre ref={preRef} className={styles.thinkingText}>
        {text}
      </pre>
    </details>
  );
}

function Spinner({ large = false }: { large?: boolean }) {
  return (
    <span
      className={`${styles.spinner} ${large ? styles.spinnerLarge : ""}`}
      role="status"
      aria-label="Ładowanie"
    />
  );
}
