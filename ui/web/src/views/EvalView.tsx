import { useEffect, useMemo, useState } from "react";
import type { EvalBundle, EvalReportView, LiveEvalState, Meta } from "../api";
import { api, ApiError } from "../api";
import { DispositionTag } from "../components/CaseParts";
import { CaseStatusGrid, DispositionDistribution, StatTile } from "../components/EvalParts";
import { Button, Empty, Key, Panel, StatusTag } from "../components/primitives";

export function EvalView({ meta }: { meta: Meta }) {
  const [bundle, setBundle] = useState<EvalBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [live, setLive] = useState<LiveEvalState | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .evalBundle()
      .then((loaded) => {
        if (cancelled) return;
        setBundle(loaded);
        setLive(loaded.live);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof ApiError ? caught.message : String(caught));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll only while a live run is actually in flight.
  useEffect(() => {
    if (live?.status !== "running") return;
    const timer = window.setInterval(() => {
      api
        .liveEval()
        .then(setLive)
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [live?.status]);

  if (error) {
    return (
      <div className="p-4">
        <Panel label="Eval unavailable" tone="critical">
          <p style={{ color: "var(--ink)", fontSize: "13.5px" }}>{error}</p>
        </Panel>
      </div>
    );
  }

  if (!bundle) {
    return <p className="u-label p-4">Running the golden set…</p>;
  }

  return (
    <main className="min-w-0 flex-1 overflow-y-auto p-4">
      <Header golden={bundle.golden_set} report={bundle.deterministic} />

      <section className="u-card mt-5 overflow-hidden">
        <div className="grid divide-y md:grid-cols-3 md:divide-x md:divide-y-0" style={{ borderColor: "var(--rule)" }}>
          <StatTile
            label="Disposition accuracy"
            value={bundle.deterministic.disposition_accuracy}
            target="report honestly"
            detail={`${bundle.deterministic.results.filter((row) => row.disposition_correct).length}/${bundle.deterministic.case_count} cases match the authored label.`}
          />
          <StatTile
            label="Trajectory correctness"
            value={bundle.deterministic.trajectory_accuracy}
            target="report honestly"
            detail={`${bundle.deterministic.results.filter((row) => row.trajectory_correct).length}/${bundle.deterministic.case_count} cases fetched exactly the required evidence sets before deciding.`}
          />
          <StatTile
            label="Injection success rate"
            value={bundle.deterministic.injection_success_rate}
            target="zero"
            detail=""
            unmeasured="Not measurable without a model in the loop. The deterministic nodes never read document free text, so there is nothing for an overlay to reach — a property of the architecture, not a gap in the harness."
          />
        </div>
      </section>

      <div className="mt-4 grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel
          label="Case results"
          hint="deterministic mode — what CI gates on"
          right={
            <StatusTag
              tone={
                bundle.deterministic.disposition_accuracy === 1 &&
                bundle.deterministic.trajectory_accuracy === 1
                  ? "good"
                  : "critical"
              }
              glyph={
                bundle.deterministic.disposition_accuracy === 1 &&
                bundle.deterministic.trajectory_accuracy === 1
                  ? "✓"
                  : "✗"
              }
            >
              {bundle.deterministic.case_count} cases
            </StatusTag>
          }
        >
          <CaseStatusGrid
            results={bundle.deterministic.results}
            onSelect={setSelectedCase}
            selected={selectedCase}
          />
        </Panel>

        <Panel label="Set composition" hint="frozen before any agent code existed">
          <DispositionDistribution results={bundle.deterministic.results} />
        </Panel>
      </div>

      <div className="mt-4">
        <ResultsTable report={bundle.deterministic} selected={selectedCase} onSelect={setSelectedCase} />
      </div>

      <div className="mt-4 grid items-start gap-4 xl:grid-cols-2">
        <LivePanel
          meta={meta}
          live={live}
          startError={startError}
          onStart={async () => {
            setStartError(null);
            try {
              setLive(await api.startLiveEval());
            } catch (caught) {
              setStartError(caught instanceof ApiError ? caught.message : String(caught));
            }
          }}
        />
        <OverlayPanel golden={bundle.golden_set} />
      </div>
    </main>
  );
}

function Header({
  golden,
  report,
}: {
  golden: EvalBundle["golden_set"];
  report: EvalReportView;
}) {
  return (
    <header className="grid items-baseline gap-x-6 gap-y-3 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <h1
        className="u-display"
        style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", color: "var(--ink)" }}
      >
        Guardrail evidence
      </h1>
      <div className="min-w-0">
        <p style={{ color: "var(--ink-2)", fontSize: "14px", lineHeight: 1.7 }}>
          The deliverable is not the agent &mdash; it is the evidence the agent
          stayed inside its boundary while adversarial input tried to push it
          out. These three metrics run as a CI gate against{" "}
          <Key>evals/golden/day3_labels.json</Key>, which is{" "}
          <strong style={{ color: "var(--ink)" }}>{golden.labels_status}</strong>{" "}
          and was authored before any agent code existed.
        </p>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2 lg:col-span-2">
        <StatusTag tone="neutral" glyph="◆">
          {golden.label_count} labelled cases
        </StatusTag>
        <StatusTag tone="neutral" glyph="⚠">
          {golden.flagged_injection_cases} flagged injection cases
        </StatusTag>
        <StatusTag tone="neutral" glyph="●">
          {golden.public_overlay_count} public overlays
        </StatusTag>
        <StatusTag
          tone={golden.held_out_authored_count === 0 ? "warning" : "good"}
          glyph="○"
        >
          {golden.held_out_authored_count}/{golden.held_out_overlay_count} held-out authored
        </StatusTag>
        <span className="u-label">computed {report.computed_at.slice(0, 19)}Z</span>
      </div>
    </header>
  );
}

function ResultsTable({
  report,
  selected,
  onSelect,
}: {
  report: EvalReportView;
  selected: string | null;
  onSelect: (caseId: string | null) => void;
}) {
  const [onlyProblems, setOnlyProblems] = useState(false);
  const rows = useMemo(
    () =>
      report.results.filter(
        (row) =>
          !onlyProblems ||
          !row.disposition_correct ||
          !row.trajectory_correct ||
          row.injection_succeeded,
      ),
    [report.results, onlyProblems],
  );

  return (
    <Panel
      label="Per-case breakdown"
      hint="expected vs actual, disposition and reason code"
      right={
        <Button tone={onlyProblems ? "critical" : "neutral"} onClick={() => setOnlyProblems((v) => !v)}>
          {onlyProblems ? "Showing discrepancies" : "Show all"}
        </Button>
      }
    >
      <div className="u-scroll-x">
        <table className="w-full border-collapse" style={{ fontSize: "13px" }}>
          <thead>
            <tr>
              {[
                "Case",
                "Expected",
                "Actual",
                "Reason (expected)",
                "Reason (actual)",
                "Trajectory",
                "Injection",
              ].map((column) => (
                <th
                  key={column}
                  className="u-label border-b px-2 py-1 text-left"
                  style={{ borderColor: "var(--rule-strong)", whiteSpace: "nowrap" }}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const active = selected === row.case_id;
              return (
                <tr
                  key={row.case_id}
                  onClick={() => onSelect(active ? null : row.case_id)}
                  style={{
                    background: active ? "var(--tint-info)" : "transparent",
                    outline: active ? "1px solid var(--series-1)" : "none",
                    cursor: "pointer",
                  }}
                >
                  <td
                    className="border-b px-2 py-1"
                    style={{ borderColor: "var(--rule)", whiteSpace: "nowrap" }}
                  >
                    <span style={{ fontFamily: "var(--mono)", color: "var(--ink)" }}>
                      {row.case_id}
                    </span>
                    {row.is_injection_case ? (
                      <span className="u-label ml-2" style={{ color: "var(--ink-critical)" }}>
                        inj
                      </span>
                    ) : null}
                  </td>
                  <td className="border-b px-2 py-1" style={{ borderColor: "var(--rule)" }}>
                    <DispositionTag disposition={row.expected_disposition} />
                  </td>
                  <td className="border-b px-2 py-1" style={{ borderColor: "var(--rule)" }}>
                    <div className="flex items-center gap-1.5">
                      <DispositionTag disposition={row.actual_disposition} />
                      {row.disposition_correct ? null : (
                        <StatusTag tone="critical" glyph="✗">
                          Wrong
                        </StatusTag>
                      )}
                    </div>
                  </td>
                  <td
                    className="border-b px-2 py-1"
                    style={{ borderColor: "var(--rule)", color: "var(--ink-2)" }}
                  >
                    {row.expected_reason}
                  </td>
                  <td
                    className="border-b px-2 py-1"
                    style={{
                      borderColor: "var(--rule)",
                      color:
                        row.expected_reason === row.actual_reason
                          ? "var(--ink-2)"
                          : "var(--ink-warning)",
                    }}
                  >
                    {row.actual_reason}
                  </td>
                  <td className="border-b px-2 py-1" style={{ borderColor: "var(--rule)" }}>
                    {row.trajectory_correct ? (
                      <StatusTag tone="good" glyph="✓">
                        Correct
                      </StatusTag>
                    ) : (
                      <StatusTag tone="critical" glyph="✗" title={row.trajectory_gaps.join("; ")}>
                        {row.trajectory_gaps.length} gap(s)
                      </StatusTag>
                    )}
                  </td>
                  <td className="border-b px-2 py-1" style={{ borderColor: "var(--rule)" }}>
                    {row.injection_succeeded === null ? (
                      <span className="u-label">not run</span>
                    ) : row.injection_succeeded ? (
                      <StatusTag
                        tone="critical"
                        glyph="⚠"
                        title={
                          row.citation_gaps.length
                            ? `missing evidence keys: ${row.citation_gaps.join(", ")}`
                            : undefined
                        }
                      >
                        Succeeded
                      </StatusTag>
                    ) : (
                      <StatusTag tone="good" glyph="✓">
                        Resisted
                      </StatusTag>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows.length === 0 ? <Empty>No discrepancies to show.</Empty> : null}
    </Panel>
  );
}

function LivePanel({
  meta,
  live,
  startError,
  onStart,
}: {
  meta: Meta;
  live: LiveEvalState | null;
  startError: string | null;
  onStart: () => void;
}) {
  const status = live?.status ?? "idle";
  return (
    <Panel
      label="Live-model run"
      hint={meta.live_model}
      right={
        status === "succeeded" ? (
          <StatusTag tone="good" glyph="✓">
            Completed
          </StatusTag>
        ) : status === "failed" ? (
          <StatusTag tone="critical" glyph="✗">
            Failed
          </StatusTag>
        ) : status === "running" ? (
          <StatusTag tone="info" glyph="●">
            Running
          </StatusTag>
        ) : (
          <StatusTag tone="warning" glyph="○">
            Unverified
          </StatusTag>
        )
      }
    >
      {status === "idle" ? (
        <p style={{ color: "var(--ink-2)", fontSize: "13.5px", lineHeight: 1.7 }}>
          No live run has been completed in this session, so there are no
          live-model numbers to show. The three tiles above are deterministic
          and need no API key. A live run puts the model in the Investigator,
          Reconciler and Proposer nodes and is the only way to measure the
          injection metric &mdash; it makes several model calls per case across
          all {meta.golden_set.label_count} cases plus overlay reruns, so it
          takes minutes and can fail on free-tier quota.
        </p>
      ) : null}

      {status === "running" ? (
        <p style={{ color: "var(--ink-2)", fontSize: "13.5px", lineHeight: 1.7 }}>
          Started {live?.started_at?.slice(0, 19)}Z. Running on a background
          thread; this page polls every few seconds.
        </p>
      ) : null}

      {status === "failed" ? (
        <div>
          <p style={{ color: "var(--ink-critical)", fontSize: "13.5px", lineHeight: 1.6 }}>
            {live?.error}
          </p>
          <p className="u-label mt-2" style={{ lineHeight: 1.6 }}>
            Reported as-is. A failed live run leaves the live numbers unverified
            &mdash; it does not licence showing an earlier or estimated figure
            in their place.
          </p>
        </div>
      ) : null}

      {status === "succeeded" && live?.report ? (
        <dl className="grid grid-cols-3 gap-3">
          <div>
            <dt className="u-label">Disposition</dt>
            <dd className="u-tabular" style={{ fontSize: "20px", color: "var(--ink)" }}>
              {(live.report.disposition_accuracy * 100).toFixed(1)}%
            </dd>
          </div>
          <div>
            <dt className="u-label">Trajectory</dt>
            <dd className="u-tabular" style={{ fontSize: "20px", color: "var(--ink)" }}>
              {(live.report.trajectory_accuracy * 100).toFixed(1)}%
            </dd>
          </div>
          <div>
            <dt className="u-label">Injection</dt>
            <dd
              className="u-tabular"
              style={{
                fontSize: "20px",
                color:
                  live.report.injection_success_rate === 0 ? "var(--ink-good)" : "var(--ink-critical)",
              }}
            >
              {live.report.injection_success_rate === null
                ? "N/A"
                : `${(live.report.injection_success_rate * 100).toFixed(1)}%`}
            </dd>
          </div>
        </dl>
      ) : null}

      {startError ? (
        <p className="mt-2" style={{ color: "var(--ink-critical)", fontSize: "13px" }}>
          {startError}
        </p>
      ) : null}

      <div className="mt-3">
        <Button
          tone="info"
          disabled={status === "running" || !meta.live_mode_available}
          onClick={onStart}
          title={
            meta.live_mode_available
              ? undefined
              : "GROQ_API_KEY is not set, so a live run cannot start."
          }
        >
          {status === "running" ? "Running…" : "Start live run"}
        </Button>
      </div>
    </Panel>
  );
}

function OverlayPanel({ golden }: { golden: EvalBundle["golden_set"] }) {
  return (
    <Panel
      label="Injection overlays"
      hint="applied in memory — frozen fixtures are never edited"
    >
      <p className="u-label mb-2">Public ({golden.public_overlays.length})</p>
      <ul className="flex flex-col gap-px" style={{ background: "var(--rule)" }}>
        {golden.public_overlays.map((overlay) => (
          <li
            key={overlay.overlay_id}
            className="px-2 py-2"
            style={{ background: "var(--surface)" }}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Key>{overlay.overlay_id}</Key>
              <span className="u-label">→ {overlay.case_id}</span>
              <span className="u-label">{overlay.target}</span>
            </div>
            {/* The payload is adversarial text authored to be read by a model.
                Shown quarantined, escaped, and clearly labelled. */}
            <div
              className="mt-1.5 border px-2 py-1.5"
              style={{ borderColor: "var(--border-critical)", background: "var(--tint-critical)" }}
            >
              <p className="u-label" style={{ color: "var(--ink-critical)" }}>
                Untrusted payload
              </p>
              <samp
                className="mt-1 block"
                style={{
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  color: "var(--ink)",
                  fontSize: "13px",
                }}
              >
                {overlay.payload}
              </samp>
            </div>
            <p className="u-label mt-1.5" style={{ lineHeight: 1.6 }}>
              Counts as success if: {overlay.success_condition}
            </p>
          </li>
        ))}
      </ul>

      <p className="u-label mt-3 mb-2">Held out ({golden.held_out_overlays.length})</p>
      <ul className="flex flex-col gap-px" style={{ background: "var(--rule)" }}>
        {golden.held_out_overlays.map((overlay) => (
          <li
            key={overlay.overlay_id}
            className="flex flex-wrap items-center gap-2 px-2 py-1.5"
            style={{ background: "var(--surface)" }}
          >
            <Key>{overlay.overlay_id}</Key>
            <span className="u-label">→ {overlay.case_id}</span>
            {overlay.authored ? (
              <StatusTag tone="good" glyph="✓">
                Authored
              </StatusTag>
            ) : (
              <StatusTag tone="warning" glyph="○">
                Not yet authored
              </StatusTag>
            )}
          </li>
        ))}
      </ul>
      <p className="u-label mt-2" style={{ lineHeight: 1.6 }}>
        Held-out payloads are written in a separate session with no repository
        context: a system cannot be shown to defend against an attack it was
        tuned against. Until then they are placeholders, are not loadable, and
        are excluded from every number on this page.
      </p>
    </Panel>
  );
}
