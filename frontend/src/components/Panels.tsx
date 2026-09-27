/** Shared shells: panels, empty, loading, and error states. */
import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="min-h-0 flex-1 p-4">{children}</div>
    </section>
  );
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <Inbox size={22} className="text-ink-faint" />
      <p className="text-sm font-medium text-ink">{title}</p>
      {detail && <p className="max-w-md text-sm text-ink-muted">{detail}</p>}
      {action}
    </div>
  );
}

export function Loading({ label = "Working…" }: { label?: string }) {
  return (
    <div
      className="flex items-center gap-2 text-sm text-ink-muted"
      role="status"
      aria-live="polite"
    >
      <Loader2 size={16} className="animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({
  title = "Something failed",
  message,
  action,
}: {
  title?: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div
      className="flex items-start gap-3 rounded-lg border px-4 py-3"
      style={{ borderColor: "var(--danger)", background: "rgba(255,107,107,0.08)" }}
      role="alert"
    >
      <AlertCircle
        size={18}
        style={{ color: "var(--danger)" }}
        className="mt-0.5 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="mt-1 text-sm text-ink-muted">{message}</p>
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

export function Callout({
  tone = "info",
  children,
}: {
  tone?: "info" | "warn";
  children: ReactNode;
}) {
  const color = tone === "warn" ? "var(--warn)" : "var(--accent)";
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs text-ink-muted"
      style={{ borderColor: color, background: "var(--surface-sunken)" }}
    >
      {children}
    </div>
  );
}
