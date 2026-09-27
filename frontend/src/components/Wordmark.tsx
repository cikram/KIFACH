/** The KIFACH wordmark: a signal that resolves into a checked step. */
export function Wordmark({
  size = 28,
  withTagline = false,
}: {
  size?: number;
  withTagline?: boolean;
}) {
  return (
    <span className="flex items-center gap-3">
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        role="img"
        aria-label="KIFACH"
        className="shrink-0"
      >
        <rect
          x="1"
          y="1"
          width="30"
          height="30"
          rx="8"
          fill="var(--surface-sunken)"
          stroke="var(--line)"
        />
        <path
          d="M8 22 V10"
          stroke="var(--ink-muted)"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <path
          d="M8 16 L15 10"
          stroke="var(--ink-muted)"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <path
          d="M13 17 l4.5 4.5 L25 10.5"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="flex flex-col leading-none">
        <span
          className="font-semibold tracking-[0.22em] text-ink"
          style={{ fontSize: size * 0.62 }}
        >
          KIFACH
        </span>
        {withTagline && (
          <span className="mt-1 text-xs tracking-wide text-ink-muted">
            Show once. Teach forever.
          </span>
        )}
      </span>
    </span>
  );
}
