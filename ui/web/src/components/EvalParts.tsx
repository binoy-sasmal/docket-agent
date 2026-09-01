import type { CaseResultRow, Disposition } from "../api";
import { DISPOSITION_LABEL } from "./CaseParts";
import { StatusTag } from "./primitives";

/**
 * A headline rate.
 *
 * These are single numbers, so they are stat tiles -- not a three-bar chart.
 * A bar chart of three near-identical rates would spend the reader's whole
 * attention budget on comparing bars that are the same length.
 *
 * `value === null` is a real state, not zero: the injection metric is
 * genuinely unmeasurable without a model in the loop, and rendering it as 0%
 * would claim a passing result the run did not produce.
 */
export function StatTile({
  label,
  value,
  detail,
  target,
  unmeasured,
}: {
  label: string;
  value: number | null;
  detail: string;
  target: string;
  unmeasured?: string;
}) {
  const measured = value !== null;
  const percent = measured ? `${(value * 100).toFixed((value * 100) % 1 === 0 ? 0 : 1)}%` : "N/A";
  return (
    <div
      className="flex min-w-0 flex-col p-4"
      style={{ background: "var(--surface)" }}
    >
      {/* The label block is height-locked so the hero figures sit on one line
          across all three tiles, however many lines a label wraps to. */}
      <h3 style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--ink-2)" }}>{label}</h3>
      <output
        className="u-tabular block"
        style={{
          fontFamily: "var(--sans)",
          fontWeight: 700,
          letterSpacing: "-0.03em",
          lineHeight: 1,
          fontSize: "clamp(2rem, 4vw, 2.75rem)",
          color: measured ? "var(--ink)" : "var(--ink-muted)",
        }}
      >
        {percent}
      </output>
      <p className="u-label mt-3 flex-1" style={{ lineHeight: 1.6 }}>
        {measured ? detail : unmeasured}
      </p>
      <p className="u-label mt-3 border-t pt-2.5" style={{ borderColor: "var(--rule)" }}>
        Target: {target}
      </p>
    </div>
  );
}

/* --- Disposition distribution -------------------------------------------- */

const ORDER: Disposition[] = ["post", "hold", "request_credit_memo", "escalate", "route"];

/**
 * Composition of the golden set by disposition.
 *
 * One hue for every bar. These are nominal categories -- bar length already
 * encodes the count, so shading each bar darker-where-bigger would double-
 * encode the same variable and burn the only free channel.
 *
 * Square mark ends are a deliberate departure from the default mark spec's
 * 4px rounded ends: this interface commits to 90-degree geometry throughout,
 * and cap shape is a refinement rather than a legibility rule. The parts that
 * do carry legibility -- thin marks, a 2px gap between adjacent bars,
 * recessive axis, direct value labels -- are kept.
 */
export function DispositionDistribution({ results }: { results: CaseResultRow[] }) {
  const counts = ORDER.map((disposition) => ({
    disposition,
    count: results.filter((row) => row.expected_disposition === disposition).length,
  }));
  const max = Math.max(1, ...counts.map((entry) => entry.count));

  const rowHeight = 30;
  const gap = 2;
  const barHeight = rowHeight - gap * 2;
  const labelWidth = 168;
  const valueWidth = 34;
  const width = 560;
  const plotWidth = width - labelWidth - valueWidth;
  const height = counts.length * rowHeight;

  return (
    <figure className="m-0">
      <figcaption className="u-label mb-2">
        Golden set composition &mdash; {results.length} labelled cases by
        authored disposition
      </figcaption>
      <div className="u-scroll-x">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Count of golden cases by expected disposition"
          style={{ maxWidth: "100%", height: "auto" }}
        >
          {/* Recessive baseline, no gridlines: five values read fine without them. */}
          <line
            x1={labelWidth}
            y1={0}
            x2={labelWidth}
            y2={height}
            stroke="var(--rule-strong)"
            strokeWidth={1}
          />
          {counts.map((entry, index) => {
            const y = index * rowHeight;
            const barWidth = (entry.count / max) * plotWidth;
            return (
              <g key={entry.disposition}>
                <title>
                  {DISPOSITION_LABEL[entry.disposition]}: {entry.count} of{" "}
                  {results.length} cases
                </title>
                <text
                  x={labelWidth - 8}
                  y={y + rowHeight / 2}
                  textAnchor="end"
                  dominantBaseline="central"
                  fill="var(--ink-2)"
                  style={{ fontFamily: "var(--sans)", fontSize: "13px" }}
                >
                  {DISPOSITION_LABEL[entry.disposition]}
                </text>
                <rect
                  x={labelWidth + 1}
                  y={y + gap}
                  width={Math.max(barWidth, entry.count > 0 ? 3 : 0)}
                  height={barHeight}
                  rx={3}
                  fill="var(--series-1)"
                />
                <text
                  x={labelWidth + Math.max(barWidth, 2) + 8}
                  y={y + rowHeight / 2}
                  dominantBaseline="central"
                  fill="var(--ink)"
                  style={{
                    fontFamily: "var(--sans)",
                    fontSize: "13px",
                    fontWeight: 600,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {entry.count}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}

/* --- Per-case status grid ------------------------------------------------ */

export function CaseStatusGrid({
  results,
  onSelect,
  selected,
}: {
  results: CaseResultRow[];
  onSelect: (caseId: string | null) => void;
  selected: string | null;
}) {
  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {results.map((row) => {
          const ok = row.disposition_correct && row.trajectory_correct;
          const color = ok ? "var(--ink-good)" : "var(--ink-critical)";
          const tint = ok ? "var(--tint-good)" : "var(--tint-critical)";
          const edge = ok ? "var(--border-good)" : "var(--border-critical)";
          const active = selected === row.case_id;
          return (
            <button
              key={row.case_id}
              type="button"
              onClick={() => onSelect(active ? null : row.case_id)}
              title={`${row.case_id} — disposition ${
                row.disposition_correct ? "correct" : "WRONG"
              }, trajectory ${row.trajectory_correct ? "correct" : "WRONG"}`}
              className="flex items-center justify-center border"
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "var(--radius-sm)",
                borderColor: active ? "var(--ink)" : edge,
                background: active ? "var(--surface-3)" : tint,
                color,
                fontSize: "14px",
                lineHeight: 1,
              }}
            >
              {/* A glyph, not colour alone. */}
              <span aria-hidden="true">{ok ? "✓" : "✗"}</span>
              <span className="sr-only">
                {row.case_id} {ok ? "pass" : "fail"}
              </span>
            </button>
          );
        })}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <StatusTag tone="good" glyph="&#10003;">
          Disposition and trajectory both correct
        </StatusTag>
        <StatusTag tone="critical" glyph="&#10007;">
          At least one wrong
        </StatusTag>
      </div>
    </div>
  );
}
