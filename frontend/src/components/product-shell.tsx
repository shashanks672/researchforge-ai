"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { SystemStatus } from "../lib/system";
import { Icon, type IconName } from "./icons";

const destinations: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "New research", icon: "plus" },
  { href: "/research", label: "History", icon: "history" },
  { href: "/library", label: "Library", icon: "library" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

function providerLabel(status: SystemStatus | null) {
  if (!status) return "Checking local setup";
  if (status.execution_mode === "local")
    return `Local AI · ${status.model ?? "Ollama"}`;
  if (status.execution_mode === "mock") return "Demo mode";
  if (status.execution_mode === "live") return "Hosted AI enabled";
  return "Research unavailable";
}

function activePath(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function ProductShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const previousPath = useRef(pathname);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/system", {
      cache: "no-store",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Local setup unavailable");
        return (await response.json()) as SystemStatus;
      })
      .then((data) => {
        if (!controller.signal.aborted) setStatus(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setStatus(null);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (previousPath.current === pathname) return;
    previousPath.current = pathname;
    const timer = window.setTimeout(() => setMenuOpen(false), 0);
    return () => window.clearTimeout(timer);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  const nav = (
    <>
      <Link className="brand" href="/" aria-label="ResearchForge home">
        <span className="brand-symbol" aria-hidden="true">
          <Icon name="spark" size={21} />
        </span>
        <span>ResearchForge</span>
      </Link>
      <nav className="primary-nav" aria-label="Primary navigation">
        <p className="nav-caption">WORKSPACE</p>
        {destinations.map((item) => (
          <Link
            key={item.href}
            className={`nav-link${activePath(pathname, item.href) ? " is-active" : ""}`}
            href={item.href}
            aria-current={activePath(pathname, item.href) ? "page" : undefined}
            onClick={() => setMenuOpen(false)}
          >
            <Icon name={item.icon} size={18} />
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="provider-summary">
          <span className="provider-indicator" aria-hidden="true" />
          <span>
            <strong>{providerLabel(status)}</strong>
            <small>
              {status?.search_provider === "disabled"
                ? "Document research available"
                : status?.search_provider === "wikipedia"
                  ? "Public web search enabled"
                  : status?.search_provider === "mock"
                    ? "Synthetic demo sources"
                    : "On this device"}
            </small>
          </span>
        </div>
        <p className="sidebar-footnote">
          Your research, in one quiet workspace.
        </p>
      </div>
    </>
  );

  return (
    <div className="product-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="desktop-sidebar">{nav}</aside>
      <div className="mobile-bar">
        <Link className="brand" href="/" aria-label="ResearchForge home">
          <span className="brand-symbol" aria-hidden="true">
            <Icon name="spark" size={21} />
          </span>
          <span>ResearchForge</span>
        </Link>
        <button
          className="icon-button mobile-menu-button"
          type="button"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          aria-controls="mobile-navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <Icon name={menuOpen ? "close" : "menu"} />
        </button>
      </div>
      {menuOpen && (
        <>
          <button
            className="mobile-scrim"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="mobile-drawer" id="mobile-navigation">
            {nav}
          </aside>
        </>
      )}
      <div className="workspace-column">
        <header className="workspace-topbar">
          <div className="breadcrumbs">
            <span>Research workspace</span>
            <span className="breadcrumb-separator" aria-hidden="true">
              /
            </span>
            <span className="breadcrumb-current">
              {pathname === "/"
                ? "New research"
                : pathname.startsWith("/research/")
                  ? "Research report"
                  : pathname === "/research"
                    ? "History"
                    : pathname === "/library"
                      ? "Library"
                      : "Settings"}
            </span>
          </div>
          <Link className="topbar-provider" href="/settings">
            <span className="provider-indicator" aria-hidden="true" />
            {providerLabel(status)}
          </Link>
        </header>
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="workspace-footer">
          <span>ResearchForge</span>
          <span>Follow the evidence. Keep the questions open.</span>
        </footer>
      </div>
    </div>
  );
}
