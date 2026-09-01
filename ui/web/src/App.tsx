import { useEffect, useState } from "react";
import type { CaseEntry, Meta } from "./api";
import { api, ApiError } from "./api";
import { CaseView } from "./views/CaseView";
import { EvalView } from "./views/EvalView";
import { StatusTag } from "./components/primitives";

type Tab = "case" | "eval";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [cases, setCases] = useState<CaseEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("case");

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.meta(), api.cases()])
      .then(([loadedMeta, loadedCases]) => {
        if (cancelled) return;
        setMeta(loadedMeta);
        setCases(loadedCases.cases);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : String(caught));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div
          className="max-w-lg border p-4"
          style={{ borderColor: "var(--border-critical)", background: "var(--surface)" }}
        >
          <p className="u-label-ink" style={{ color: "var(--ink-critical)" }}>
            Cannot reach the Docket API
          </p>
          <p className="mt-2" style={{ color: "var(--ink)", fontSize: "13.5px", lineHeight: 1.6 }}>
            {error}
          </p>
          <p className="u-label mt-3" style={{ lineHeight: 1.6 }}>
            Start it with:{" "}
            <code style={{ color: "var(--ink-2)" }}>
              uvicorn ui.api.app:app --port 8000 --workers 1
            </code>
          </p>
        </div>
      </div>
    );
  }

  if (!meta) {
    return <p className="u-label p-6">Connecting…</p>;
  }

  return (
    <div className="flex h-full flex-col">
      <Header meta={meta} tab={tab} onTab={setTab} />
      {tab === "case" ? <CaseView meta={meta} cases={cases} /> : <EvalView meta={meta} />}
    </div>
  );
}

function Header({
  meta,
  tab,
  onTab,
}: {
  meta: Meta;
  tab: Tab;
  onTab: (tab: Tab) => void;
}) {
  return (
    <header
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b px-5 py-3"
      style={{ borderColor: "var(--rule)", background: "var(--surface)" }}
    >
      <div className="flex items-baseline gap-2.5">
        <span className="u-display" style={{ fontSize: "18px", color: "var(--ink)" }}>
          Docket
        </span>
        <span className="u-label">Invoice-exception agent</span>
      </div>

      {/* Segmented control: a filled pill for the current view reads as
          "where I am" far faster than a 2px top rule on a tinted tab. */}
      <nav
        className="flex gap-1 p-1"
        style={{ background: "var(--surface-3)", borderRadius: "8px" }}
        aria-label="Views"
      >
        {(
          [
            ["case", "Case & approval"],
            ["eval", "Guardrail evidence"],
          ] as const
        ).map(([value, label]) => {
          const active = tab === value;
          return (
            <button
              key={value}
              type="button"
              onClick={() => onTab(value)}
              aria-current={active ? "page" : undefined}
              className="transition-colors duration-150"
              style={{
                minHeight: "32px",
                padding: "0 14px",
                borderRadius: "6px",
                background: active ? "var(--surface)" : "transparent",
                color: active ? "var(--ink)" : "var(--ink-2)",
                boxShadow: active ? "var(--shadow-sm)" : "none",
                fontSize: "13.5px",
                fontWeight: active ? 600 : 500,
              }}
            >
              {label}
            </button>
          );
        })}
      </nav>

      <div className="flex flex-wrap items-center gap-2">
        <StatusTag tone="good" glyph="&#128274;" title={meta.can_post_note}>
          Cannot post
        </StatusTag>
        <StatusTag
          tone={meta.live_mode_available ? "info" : "neutral"}
          glyph={meta.live_mode_available ? "●" : "○"}
          title={
            meta.live_mode_available
              ? `Live mode available on ${meta.live_model}`
              : "GROQ_API_KEY not set — deterministic mode only"
          }
        >
          {meta.live_mode_available ? "Live available" : "Deterministic only"}
        </StatusTag>
        <StatusTag tone="neutral" glyph="◇" title={meta.persistence_note}>
          In-process state
        </StatusTag>
      </div>
    </header>
  );
}
