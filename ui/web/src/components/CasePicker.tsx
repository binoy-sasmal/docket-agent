import { useMemo, useState } from "react";
import type { CaseEntry, Meta, RunMode } from "../api";
import { Button, inputStyle, Key, StatusTag } from "./primitives";
import { DispositionTag } from "./CaseParts";

type Filter = "golden" | "injection" | "all";

/**
 * Case selection: pick from the frozen selection, or type a PO + item.
 *
 * Golden-label columns are marked as labels, never mixed in with agent output.
 * They are the authored ground truth the run is scored against; showing them
 * as though the agent produced them would be the UI equivalent of an agent
 * grading its own homework.
 */
export function CasePicker({
  cases,
  meta,
  mode,
  overlayId,
  busy,
  selectedCaseId,
  onModeChange,
  onOverlayChange,
  onRun,
}: {
  cases: CaseEntry[];
  meta: Meta;
  mode: RunMode;
  overlayId: string | null;
  busy: boolean;
  selectedCaseId: string | null;
  onModeChange: (mode: RunMode) => void;
  onOverlayChange: (overlayId: string | null) => void;
  onRun: (entry: { purchase_order: string; purchase_order_item: string }) => void;
}) {
  const [filter, setFilter] = useState<Filter>("golden");
  const [query, setQuery] = useState("");
  const [manualPo, setManualPo] = useState("");
  const [manualItem, setManualItem] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return cases
      .filter((entry) => {
        if (filter === "golden" && !entry.in_golden_set) return false;
        if (filter === "injection" && !entry.golden_is_injection_case) return false;
        if (!needle) return true;
        return (
          entry.case_id.toLowerCase().includes(needle) ||
          entry.supplier.toLowerCase().includes(needle)
        );
      })
      .slice(0, 200);
  }, [cases, filter, query]);

  const selectedOverlayCase = overlayId
    ? cases.find((entry) => entry.public_overlay_id === overlayId)
    : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b p-3" style={{ borderColor: "var(--rule)" }}>
        <p className="u-label-ink">Run configuration</p>

        <div
          className="mt-2 flex gap-1 p-1"
          style={{ background: "var(--surface-3)", borderRadius: "8px" }}
        >
          {(["deterministic", "live"] as const).map((option) => {
            const disabled = option === "live" && !meta.live_mode_available;
            const active = mode === option;
            return (
              <button
                key={option}
                type="button"
                disabled={disabled}
                onClick={() => {
                  onModeChange(option);
                  if (option === "deterministic") onOverlayChange(null);
                }}
                title={
                  disabled
                    ? "GROQ_API_KEY is not set, so no model can be put in the loop."
                    : undefined
                }
                className="flex-1 transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50"
                style={{
                  minHeight: "30px",
                  borderRadius: "6px",
                  background: active ? "var(--surface)" : "transparent",
                  color: active ? "var(--ink)" : "var(--ink-2)",
                  boxShadow: active ? "var(--shadow-sm)" : "none",
                  fontSize: "13px",
                  fontWeight: active ? 600 : 500,
                  textTransform: "capitalize",
                }}
              >
                {option}
              </button>
            );
          })}
        </div>
        <p className="u-label mt-1.5" style={{ lineHeight: 1.6 }}>
          {mode === "deterministic"
            ? "No model in the loop. Every node is deterministic and network-free — this is what CI runs."
            : `Investigator tool-calling, Reconciler narrative and Proposer justification run on ${meta.live_model}.`}
        </p>

        <div className="mt-3">
          <p className="u-label">Injection overlay</p>
          <select
            value={overlayId ?? ""}
            disabled={mode === "deterministic"}
            onChange={(event) => onOverlayChange(event.target.value || null)}
            className="mt-1 w-full border px-2 py-1.5 disabled:cursor-not-allowed disabled:opacity-40"
            style={inputStyle}
          >
            <option value="">None</option>
            {meta.golden_set.public_overlays.map((overlay) => (
              <option key={overlay.overlay_id} value={overlay.overlay_id}>
                {overlay.overlay_id} → {overlay.case_id} ({overlay.target})
              </option>
            ))}
          </select>
          <p className="u-label mt-1.5" style={{ lineHeight: 1.6 }}>
            {mode === "deterministic"
              ? "Unavailable in deterministic mode: with no model in the loop, no node reads document free text, so an overlay has nothing to reach."
              : selectedOverlayCase
                ? `Applies to case ${selectedOverlayCase.case_id} only, in memory. Frozen fixtures are never modified.`
                : "Applied to an in-memory copy of the document. The four held-out payloads stay unauthored and are not selectable."}
          </p>
          {selectedOverlayCase ? (
            <div className="mt-2">
              <Button
                tone="info"
                disabled={busy}
                onClick={() =>
                  onRun({
                    purchase_order: selectedOverlayCase.purchase_order,
                    purchase_order_item: selectedOverlayCase.purchase_order_item,
                  })
                }
              >
                Run overlay target
              </Button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="border-b p-3" style={{ borderColor: "var(--rule)" }}>
        <p className="u-label-ink">Paste a case</p>
        <div className="mt-2 flex gap-2">
          <input
            value={manualPo}
            onChange={(event) => setManualPo(event.target.value)}
            placeholder="purchase order"
            spellCheck={false}
            className="min-w-0 flex-1 border px-2 py-1.5"
            style={inputStyle}
          />
          <input
            value={manualItem}
            onChange={(event) => setManualItem(event.target.value)}
            placeholder="item"
            spellCheck={false}
            className="w-20 border px-2 py-1.5"
            style={inputStyle}
          />
        </div>
        <div className="mt-2">
          <Button
            disabled={busy || !manualPo.trim() || !manualItem.trim()}
            onClick={() =>
              onRun({
                purchase_order: manualPo.trim(),
                purchase_order_item: manualItem.trim(),
              })
            }
          >
            Run case
          </Button>
        </div>
      </div>

      <div className="border-b p-3" style={{ borderColor: "var(--rule)" }}>
        <div
          className="flex gap-1 p-1"
          style={{ background: "var(--surface-3)", borderRadius: "8px" }}
        >
          {(
            [
              ["golden", "Golden 30"],
              ["injection", "Injection"],
              ["all", "All 300"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              className="flex-1 transition-colors duration-150"
              style={{
                minHeight: "28px",
                borderRadius: "6px",
                background: filter === value ? "var(--surface)" : "transparent",
                color: filter === value ? "var(--ink)" : "var(--ink-2)",
                boxShadow: filter === value ? "var(--shadow-sm)" : "none",
                fontSize: "12.5px",
                fontWeight: filter === value ? 600 : 500,
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="filter by case id or supplier"
          spellCheck={false}
          className="mt-2 w-full border px-2 py-1.5"
          style={inputStyle}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <ul className="flex flex-col gap-px" style={{ background: "var(--rule)" }}>
          {visible.map((entry) => {
            const active = entry.case_id === selectedCaseId;
            return (
              <li key={entry.case_id} style={{ background: "var(--surface)" }}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    onRun({
                      purchase_order: entry.purchase_order,
                      purchase_order_item: entry.purchase_order_item,
                    })
                  }
                  className="w-full px-3 py-2.5 text-left transition-colors duration-150 disabled:opacity-50"
                  style={{
                    background: active ? "var(--surface-3)" : "transparent",
                    borderLeft: active
                      ? "2px solid var(--series-1)"
                      : "2px solid transparent",
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: "13px",
                        fontWeight: 500,
                        color: "var(--ink)",
                      }}
                    >
                      {entry.case_id}
                    </span>
                    {entry.golden_is_injection_case ? (
                      <StatusTag tone="critical" glyph="&#9888;">
                        Inj
                      </StatusTag>
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="u-label">{entry.supplier}</span>
                    <span className="u-label u-tabular">
                      {entry.purchase_order_amount} {entry.currency}
                    </span>
                    <span className="u-label">
                      {entry.goods_receipt_count}gr/{entry.invoice_count}inv
                    </span>
                  </div>
                  {entry.golden_disposition ? (
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span className="u-label">Expected</span>
                      <DispositionTag disposition={entry.golden_disposition} />
                    </div>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
        {visible.length === 0 ? (
          <p className="u-label p-3">No case matches that filter.</p>
        ) : null}
        <p className="u-label p-3" style={{ lineHeight: 1.6 }}>
          Frozen selection: <Key>{cases.length}</Key> cases, of which{" "}
          <Key>{cases.filter((entry) => entry.in_golden_set).length}</Key> carry
          a golden label. Showing at most 200.
        </p>
      </div>
    </div>
  );
}
