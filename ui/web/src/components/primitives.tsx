import type { ReactNode } from "react";

/**
 * Shared structural pieces.
 *
 * Panels are cards on a tinted page rather than hairline compartments on a
 * dark ground: the separation now comes from surface and a soft shadow, which
 * carries the same "these things are different" signal with far less contrast
 * noise per square inch.
 */

export function Panel({
  label,
  hint,
  right,
  children,
  tone = "default",
  className = "",
}: {
  label: string;
  hint?: string;
  right?: ReactNode;
  children: ReactNode;
  tone?: "default" | "critical";
  className?: string;
}) {
  const critical = tone === "critical";
  return (
    <section
      className={`u-card overflow-hidden ${className}`}
      style={critical ? { borderColor: "var(--border-critical)" } : undefined}
    >
      <header
        className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 border-b px-4 py-2.5"
        style={{
          borderColor: critical ? "var(--border-critical)" : "var(--rule)",
          background: critical ? "var(--tint-critical)" : "var(--surface-2)",
        }}
      >
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
          <h2
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: critical ? "var(--ink-critical)" : "var(--ink)",
            }}
          >
            {label}
          </h2>
          {hint ? <span className="u-label">{hint}</span> : null}
        </div>
        {right ? <div className="shrink-0">{right}</div> : null}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** A machine identifier -- a document key, thread id, tool name. */
export function Key({ children }: { children: ReactNode }) {
  return <span className="u-key">{children}</span>;
}

export function Field({
  label,
  value,
  mono = true,
  title,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  title?: string;
}) {
  return (
    <div className="min-w-0" title={title}>
      <dt className="u-label">{label}</dt>
      <dd
        className="mt-0.5 truncate"
        style={{
          color: "var(--ink)",
          fontSize: "13.5px",
          fontFamily: mono ? "var(--mono)" : "var(--sans)",
          fontVariantNumeric: mono ? "tabular-nums" : undefined,
        }}
      >
        {value}
      </dd>
    </div>
  );
}

export type StatusTone = "good" | "warning" | "serious" | "critical" | "neutral" | "info";

/**
 * Two colours per tone, not one.
 *
 * `mark` is the validated status hue, used for the dot and the border, where
 * the 3:1 mark floor applies. `ink` is a darkened member of the same hue
 * family for the label text, where 4.5:1 applies. On a light ground these
 * genuinely differ: the status yellow reads 1.83:1 on white as text.
 */
const TONE: Record<StatusTone, { mark: string; ink: string; tint: string; border: string }> = {
  good: {
    mark: "var(--mark-good)",
    ink: "var(--ink-good)",
    tint: "var(--tint-good)",
    border: "var(--border-good)",
  },
  warning: {
    mark: "var(--mark-warning)",
    ink: "var(--ink-warning)",
    tint: "var(--tint-warning)",
    border: "var(--border-warning)",
  },
  serious: {
    mark: "var(--mark-serious)",
    ink: "var(--ink-serious)",
    tint: "var(--tint-warning)",
    border: "var(--border-warning)",
  },
  critical: {
    mark: "var(--mark-critical)",
    ink: "var(--ink-critical)",
    tint: "var(--tint-critical)",
    border: "var(--border-critical)",
  },
  neutral: {
    mark: "var(--ink-muted)",
    ink: "var(--ink-2)",
    tint: "var(--surface-3)",
    border: "var(--rule-strong)",
  },
  info: {
    mark: "var(--series-1)",
    ink: "var(--ink-link)",
    tint: "var(--tint-info)",
    border: "var(--border-info)",
  },
};

/**
 * A state marker. Always renders a glyph AND a label beside the colour, so
 * status never depends on hue alone.
 */
export function StatusTag({
  tone,
  glyph,
  children,
  title,
}: {
  tone: StatusTone;
  glyph: string;
  children: ReactNode;
  title?: string;
}) {
  const { mark, ink, tint, border } = TONE[tone];
  return (
    <span
      className="inline-flex items-center gap-1.5 border px-2 py-0.5 align-middle"
      style={{
        borderColor: border,
        background: tint,
        color: ink,
        borderRadius: "999px",
        fontSize: "12px",
        fontWeight: 500,
        lineHeight: 1.5,
        whiteSpace: "nowrap",
      }}
      title={title}
    >
      <span aria-hidden="true" style={{ color: mark, fontSize: "11px", lineHeight: 1 }}>
        {glyph}
      </span>
      {children}
    </span>
  );
}

export function toneInk(tone: StatusTone): string {
  return TONE[tone].ink;
}

export function toneMark(tone: StatusTone): string {
  return TONE[tone].mark;
}

export function Rule({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <span className="h-px flex-1" style={{ background: "var(--rule)" }} />
      {label ? <span className="u-label">{label}</span> : null}
      <span className="h-px flex-1" style={{ background: "var(--rule)" }} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p
      className="rounded px-3 py-2.5"
      style={{
        background: "var(--surface-3)",
        color: "var(--ink-2)",
        fontSize: "13px",
        lineHeight: 1.6,
      }}
    >
      {children}
    </p>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  tone = "neutral",
  variant = "secondary",
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "neutral" | "good" | "critical" | "info";
  variant?: "primary" | "secondary";
  type?: "button" | "submit";
  title?: string;
}) {
  const accent =
    tone === "good"
      ? { solid: "#15803d", ink: "var(--ink-good)", border: "var(--border-good)", tint: "var(--tint-good)" }
      : tone === "critical"
        ? { solid: "#b91c1c", ink: "var(--ink-critical)", border: "var(--border-critical)", tint: "var(--tint-critical)" }
        : tone === "info"
          ? { solid: "#1d4ed8", ink: "var(--ink-link)", border: "var(--border-info)", tint: "var(--tint-info)" }
          : { solid: "var(--brand)", ink: "var(--ink-2)", border: "var(--rule-strong)", tint: "var(--surface-3)" };

  const primary = variant === "primary";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="inline-flex items-center justify-center gap-2 border transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50"
      style={{
        // 36px min height: comfortably clickable without wasting vertical
        // space in a tool this dense.
        minHeight: "36px",
        padding: "0 14px",
        borderRadius: "var(--radius)",
        borderColor: primary ? accent.solid : accent.border,
        background: primary ? accent.solid : "var(--surface)",
        color: primary ? "#ffffff" : accent.ink,
        fontSize: "13px",
        fontWeight: 500,
        fontFamily: "var(--sans)",
      }}
      onMouseEnter={(event) => {
        if (disabled) return;
        event.currentTarget.style.background = primary ? accent.ink : accent.tint;
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.background = primary ? accent.solid : "var(--surface)";
      }}
    >
      {children}
    </button>
  );
}

/** Text input and textarea share one look, defined once. */
export const inputStyle: React.CSSProperties = {
  borderColor: "var(--rule-strong)",
  background: "var(--surface)",
  color: "var(--ink)",
  fontFamily: "var(--sans)",
  fontSize: "13.5px",
  borderRadius: "var(--radius)",
  minHeight: "36px",
};
