"use client";

import { LockKeyhole, LogIn } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Suspense } from "react";

import { resolvePostLoginTarget, useAuth, useLoginTarget } from "@/lib/auth";

import styles from "./page.module.css";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className={styles.screen}>Ładowanie...</main>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const target = useLoginTarget();
  const { user, loading, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) {
      router.replace(resolvePostLoginTarget(user, target));
    }
  }, [loading, router, target, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const loggedInUser = await login(username, password);
      router.replace(resolvePostLoginTarget(loggedInUser, target));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się zalogować");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.screen}>
      <form className={styles.card} onSubmit={submit}>
        <div className={styles.icon} aria-hidden>
          <LockKeyhole size={22} />
        </div>
        <div className={styles.header}>
          <h1>Logowanie</h1>
          <p>Wpisz login i hasło.</p>
        </div>

        <label className={styles.field}>
          <span>Login</span>
          <input
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
          />
        </label>

        <label className={styles.field}>
          <span>Hasło</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>

        {error ? <div className={styles.error}>{error}</div> : null}

        <button
          className={styles.submit}
          type="submit"
          disabled={submitting || !username.trim() || !password}
        >
          <LogIn size={17} />
          {submitting ? "Loguję..." : "Zaloguj"}
        </button>
      </form>
    </main>
  );
}
