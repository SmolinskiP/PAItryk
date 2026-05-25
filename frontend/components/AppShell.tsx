"use client";

import {
  Database,
  LogIn,
  LogOut,
  MessageSquareText,
  Moon,
  Puzzle,
  Settings,
  Sun,
  Users
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isLanding = pathname === "/";
  const isChat = pathname === "/chat";
  const isFullbleed =
    isLanding || isChat || pathname.startsWith("/admin") || pathname === "/login" || pathname.startsWith("/riddle");
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const { user, logout } = useAuth();

  useEffect(() => {
    const saved = window.localStorage.getItem("paitryk-theme");
    const nextTheme = saved === "dark" || saved === "light" ? saved : "dark";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
  }, []);

  function toggleTheme() {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem("paitryk-theme", nextTheme);
  }

  async function handleLogout() {
    await logout();
    window.location.href = "/";
  }

  if (pathname.startsWith("/riddle")) return <>{children}</>;

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/riddle">
          <Puzzle size={17} />
          <span>My?tery</span>
        </Link>
        <nav className="nav" aria-label="Główna nawigacja">
          {user ? (
            <>
              {user.role === "admin" ? (
                <>
                  <Link href="/chat">
                    <MessageSquareText size={17} />
                    <span className="nav-label">Chat</span>
                  </Link>
                  <Link href="/admin">
                    <Settings size={17} />
                    <span className="nav-label">Admin</span>
                  </Link>
                  <Link href="/users">
                    <Users size={17} />
                    <span className="nav-label">Userzy</span>
                  </Link>
                  <Link href="/admin/memory">
                    <Database size={17} />
                    <span className="nav-label">Memory</span>
                  </Link>
                </>
              ) : null}
              <span className="nav-user">{user.username}</span>
              <button className="theme-toggle" onClick={handleLogout} type="button" aria-label="Wyloguj">
                <LogOut size={17} />
                <span className="nav-label">Wyloguj</span>
              </button>
            </>
          ) : pathname !== "/login" ? (
            <Link href="/login">
              <LogIn size={17} />
              <span className="nav-label">Logowanie</span>
            </Link>
          ) : null}
          <button className="theme-toggle" onClick={toggleTheme} type="button" aria-label={theme === "light" ? "Włącz tryb ciemny" : "Włącz tryb jasny"}>
            {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            <span className="nav-label">{theme === "light" ? "Ciemny" : "Jasny"}</span>
          </button>
        </nav>
      </header>
      <main className={isFullbleed ? "workspace fullbleed" : "workspace"}>{children}</main>
    </div>
  );
}
