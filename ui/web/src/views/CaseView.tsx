import { useState } from "react";
import type { CaseEntry, DecisionResponse, MemoryRecord, Meta, RunMode, RunView } from "../api";
import { api, ApiError } from "../api";
import { ApprovalBar, SupplierMemoryPanel } from "../components/ApprovalBar";
import {
  ClaimsPanel,
  DispositionTag,
  DocumentsPanel,
  PolicyPanel,
  ProposalPanel,
  StageRail,
  TrajectoryPanel,
} from "../components/CaseParts";
import { CasePicker } from "../components/CasePicker";
import { Key, Panel, StatusTag } from "../components/primitives";
import { UntrustedNotes } from "../components/UntrustedNote";

export function CaseView({ meta, cases }: { meta: Meta; cases: CaseEntry[] }) {
  const [mode, setMode] = useState<RunMode>("deterministic");
  const [overlayId, setOverlayId] = useState<string | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [memory, setMemory] = useState<MemoryRecord[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startRun(target: { purchase_order: string; purchase_order_item: string }) {
    setBusy(true);
    setError(null);
    setSelectedKey(null);
    try {
      const created = await api.createRun({
        ...target,
        mode,
        overlay_id: overlayId,
      });
      setRun(created);
      const supplierMemory = await api.supplierMemory(created.proposal.supplier);
      setMemory(supplierMemory.records);
    } catch (caught) {
      setRun(null);
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function handleDecided(response: DecisionResponse) {
    setRun(response.run);
    setMemory(response.supplier_memory);
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside
        className="min-h-0 border-b lg:border-b-0 lg:border-r"
        style={{ borderColor: "var(--rule)", background: "var(--surface)" }}
      >
        <CasePicker
          cases={cases}
          meta={meta}
          mode={mode}
          overlayId={overlayId}
          busy={busy}
          selectedCaseId={run?.case_id ?? null}
          onModeChange={setMode}
          onOverlayChange={setOverlayId}
          onRun={startRun}
        />
      </aside>

      <main className="min-w-0 overflow-y-auto p-4">
        <StageRail matrix={meta.node_matrix} />

        {error ? (
          <div
            className="mt-4 rounded border px-4 py-3"
            style={{ borderColor: "var(--border-critical)", background: "var(--tint-critical)" }}
          >
            <p style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--ink-critical)" }}>
              Run failed
            </p>
            <p className="mt-1" style={{ color: "var(--ink)", fontSize: "13.5px" }}>
              {error}
            </p>
          </div>
        ) : null}

        {busy && !run ? (
          <p className="u-label mt-6">Running the graph…</p>
        ) : null}

        {!run && !busy && !error ? <EmptyState meta={meta} /> : null}

        {run ? (
          <div className="mt-4 flex flex-col gap-4">
            <RunHeader run={run} />

            <div className="grid items-start gap-4 xl:grid-cols-2">
              <TrajectoryPanel investigation={run.investigation} />
              <Panel
                label="Untrusted document text"
                hint="rendered as data, never as instruction"
                tone={run.investigation.untrusted_notes.length ? "critical" : "default"}
                right={
                  run.investigation.untrusted_notes.length ? (
                    <StatusTag tone="critical" glyph="&#9888;">
                      {run.investigation.untrusted_notes.length} note(s)
                    </StatusTag>
                  ) : (
                    <StatusTag tone="neutral" glyph="&#8709;">
                      None present
                    </StatusTag>
                  )
                }
              >
                <UntrustedNotes notes={run.investigation.untrusted_notes} />
              </Panel>
            </div>

            <ClaimsPanel
              claims={run.reconciliation.claims}
              narrative={run.reconciliation.narrative}
              selectedKey={selectedKey}
              onSelectKey={setSelectedKey}
            />

            <DocumentsPanel investigation={run.investigation} selectedKey={selectedKey} />

            <PolicyPanel
              policy={run.policy}
              reconciliation={run.reconciliation}
              currency={run.investigation.purchase_order_item.DocumentCurrency}
              tolerancePolicy={meta.tolerance_policy}
            />

            <ProposalPanel
              proposal={run.proposal}
              run={run}
              canPostNote={meta.can_post_note}
            />

            <ApprovalBar run={run} onDecided={handleDecided} />

            <SupplierMemoryPanel supplier={run.proposal.supplier} records={memory} />
          </div>
        ) : null}
      </main>
    </div>
  );
}

function RunHeader({ run }: { run: RunView }) {
  const golden = run.golden;
  const matchesLabel =
    golden.in_golden_set && golden.expected_disposition === run.proposal.disposition;
  return (
    <div
      className="u-card flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="u-label">Case</p>
          <p className="u-display" style={{ fontSize: "20px", color: "var(--ink)" }}>
            {run.case_id}
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <span className="u-label">Thread</span>
          <Key>{run.thread_id}</Key>
        </div>
        <div className="flex flex-col gap-1">
          <span className="u-label">Mode</span>
          <StatusTag tone={run.mode === "live" ? "info" : "neutral"} glyph="●">
            {run.mode}
          </StatusTag>
        </div>
        {run.overlay_id ? (
          <div className="flex flex-col gap-1">
            <span className="u-label">Overlay</span>
            <StatusTag tone="critical" glyph="&#9888;">
              {run.overlay_id}
            </StatusTag>
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-col items-end gap-1">
          <span className="u-label">Proposed</span>
          <DispositionTag disposition={run.proposal.disposition} />
        </div>
        {golden.in_golden_set && golden.expected_disposition ? (
          <div className="flex flex-col items-end gap-1">
            <span className="u-label">Golden label</span>
            <div className="flex items-center gap-1.5">
              <DispositionTag disposition={golden.expected_disposition} />
              {matchesLabel ? (
                <StatusTag tone="good" glyph="&#10003;">
                  Match
                </StatusTag>
              ) : (
                <StatusTag tone="critical" glyph="&#10007;">
                  Divergent
                </StatusTag>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function EmptyState({ meta }: { meta: Meta }) {
  return (
    <div className="mt-6 max-w-3xl">
      <h1
        className="u-display"
        style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)", color: "var(--ink)" }}
      >
        Exception console
      </h1>
      <p
        className="mt-4"
        style={{ color: "var(--ink-2)", fontSize: "13.5px", lineHeight: 1.7, maxWidth: "60ch" }}
      >
        Select a case to run it through the four-node graph. The run stops at a
        real LangGraph <code style={{ color: "var(--series-1)" }}>interrupt()</code>{" "}
        before the approval step, and shows you what an approver actually needs:
        which tools were called and in what order, every claim with the document
        key it rests on, the policy gate&rsquo;s arithmetic, and the proposal.
      </p>
      <div className="mt-6 flex flex-col gap-2">
        <div
          className="u-card px-4 py-3"
        >
          <p style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--ink)" }}>
            No post capability
          </p>
          <p className="mt-1" style={{ color: "var(--ink-2)", fontSize: "13px", lineHeight: 1.6 }}>
            {meta.can_post_note}
          </p>
        </div>
        <div
          className="u-card px-4 py-3"
        >
          <p style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--ink)" }}>
            Process-local state
          </p>
          <p className="mt-1" style={{ color: "var(--ink-2)", fontSize: "13px", lineHeight: 1.6 }}>
            {meta.persistence_note}
          </p>
        </div>
      </div>
    </div>
  );
}
