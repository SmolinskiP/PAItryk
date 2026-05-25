"use client";

import { ArrowRight, Database, MessageSquareText, Settings, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ProtectedRoute, useAuth } from "@/lib/auth";

import styles from "./page.module.css";

export default function ApplicationPage() {
  return (
    <ProtectedRoute roles={["user", "admin"]}>
      <ApplicationHome />
    </ProtectedRoute>
  );
}

function ApplicationHome() {
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (user?.role === "user") {
      router.replace("/chat");
    }
  }, [router, user]);

  if (user?.role === "user") {
    return <div className="route-state">Przekierowuję do czata...</div>;
  }

  return (
    <main className={styles.page}>
      <section className={styles.header}>
        <div>
          <span className={styles.kicker}>panel aplikacji</span>
          <h1>pAItryk</h1>
        </div>
        <span className={styles.badge}>{isAdmin ? "admin" : "user"}</span>
      </section>

      <section className={styles.grid}>
        <Link className={styles.tile} href="/chat">
          <MessageSquareText size={22} />
          <strong>Chat</strong>
          <span>Rozmowa z publicznym klonem.</span>
          <ArrowRight className={styles.arrow} size={18} />
        </Link>

        {isAdmin ? (
          <>
            <Link className={styles.tile} href="/admin">
              <Settings size={22} />
              <strong>Admin</strong>
              <span>Kuratorowanie pamięci, ingest i diagnostyka RAG.</span>
              <ArrowRight className={styles.arrow} size={18} />
            </Link>
            <Link className={styles.tile} href="/users">
              <Users size={22} />
              <strong>Userzy</strong>
              <span>Podgląd kont, ról i zakresów dostępu.</span>
              <ArrowRight className={styles.arrow} size={18} />
            </Link>
            <Link className={styles.tile} href="/admin/memory">
              <Database size={22} />
              <strong>Memory</strong>
              <span>Osobny widok rekordów pamięci i ręcznej edycji RAG.</span>
              <ArrowRight className={styles.arrow} size={18} />
            </Link>
          </>
        ) : null}
      </section>
    </main>
  );
}
