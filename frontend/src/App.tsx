/** The KIFACH shell: header, provider provenance, theme, and the current screen. */
import { useCallback, useEffect, useState } from "react";
import { BookOpen, Moon, PlayCircle, Sun } from "lucide-react";
import { api } from "@/lib/api";
import { useRouter } from "@/lib/router";
import type { HealthResponse } from "@/types/api";
import { Wordmark } from "@/components/Wordmark";
import { ProvenanceBadge } from "@/components/Badges";
import { HomeView } from "@/views/HomeView";
import { TeachView } from "@/views/TeachView";
import { ReviewView } from "@/views/ReviewView";
import { PracticeView } from "@/views/PracticeView";
import { VerdictView } from "@/views/VerdictView";
import { LiveView } from "@/views/LiveView";
import { DemoView } from "@/views/DemoView";

type Theme = "dark" | "light";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = window.localStorage.getItem("kifach-theme");
    return stored === "light" ? "light" : "dark";
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("kifach-theme", theme);
  }, [theme]);
  return [theme, () => setTheme((current) => (current === "dark" ? "light" : "dark"))];
}

export function App() {
  const { route, navigate } = useRouter();
  const [theme, toggleTheme] = useTheme();
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const refreshHealth = useCallback(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(refreshHealth, [refreshHealth]);

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-surface-raised focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-surface backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-3 px-4 py-3">
          <button
            type="button"
            onClick={() => navigate({ name: "home" })}
            className="rounded"
            aria-label="KIFACH home"
          >
            <Wordmark size={26} />
          </button>
          <span className="hidden text-xs text-ink-faint sm:inline">
            Show once. Teach forever.
          </span>
          <nav className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate({ name: "teach" })}
            >
              <BookOpen size={15} /> Teach
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate({ name: "demo" })}
              data-testid="nav-demo"
            >
              <PlayCircle size={15} /> Demo mode
            </button>
            {health && (
              <span className="flex items-center gap-2" data-testid="provider-status">
                <ProvenanceBadge provenance={health.provider.provenance_label} compact />
                <span className="mono hidden text-xs text-ink-faint lg:inline">
                  {health.provider.provider}
                  {health.provider.model ? ` · ${health.provider.model}` : ""}
                </span>
              </span>
            )}
            <button
              type="button"
              className="btn btn-ghost"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5">
        {route.name === "home" && <HomeView health={health} />}
        {route.name === "teach" && <TeachView health={health} />}
        {route.name === "review" && <ReviewView skillId={route.skillId} />}
        {route.name === "practice" && <PracticeView skillId={route.skillId} />}
        {route.name === "live" && <LiveView skillId={route.skillId} />}
        {route.name === "verdict" && <VerdictView attemptId={route.attemptId} />}
        {route.name === "demo" && <DemoView health={health} />}
      </main>

      <footer className="border-t border-line px-4 py-3">
        <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-3 text-xs text-ink-faint">
          <span>
            The model observes and proposes. The reviewed procedure and the deterministic
            engine decide.
          </span>
          {health && (
            <span className="mono ml-auto">
              v{health.version} · {health.provider.cache_mode} cache
            </span>
          )}
        </div>
      </footer>
    </div>
  );
}
