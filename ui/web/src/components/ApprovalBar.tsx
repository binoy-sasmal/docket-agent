import { useState } from "react";
import type { DecisionResponse, MemoryRecord, RunView } from "../api";
import { api, ApiError } from "../api";
import { Button, inputStyle, Key, Panel, StatusTag } from "./primitives";

/**
 * The human decision that resumes the graph's `interrupt()`.
 *
 * Three things this component deliberately does not do:
 *
 * 1. There is no "post" control, because there is no post capability. The
 *    affirmative action is worded as approving a proposal and recording a
 *    resolution, which is what actually happens.
 * 2. Nothing here is ever prefilled from document text. The approver types
 *    their own identity and their own reason. An injected note that says
 *    "pre-approved by finance" must not be able to reach this form, not even
 *    as a helpful default.
 * 3. `proposed_by` is not an input. It comes back from the server with the run.
 *    Segregation of duties means nothing if the same client can supply both
 *    halves of the comparison.
 */
export function ApprovalBar({
  run,
  onDecided,
}: {
  run: RunView;
  onDecided: (response: DecisionResponse) => void;
}) {
  const [approver, setApprover] = useState(
    () => window.localStorage.getItem("docket.approver") ?? "",
  );
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decided = run.status !== "awaiting_approval";
  const trimmedApprover = approver.trim();
  const trimmedReason = reason.trim();
  const sameActor = trimmedApprover !== "" && trimmedApprover === run.proposed_by;
  const ready = trimmedApprover !== "" && trimmedReason !== "" && !sameActor;

  async function submit(decision: "approve" | "reject") {
    setPending(decision);
    setError(null);
    try {
      window.localStorage.setItem("docket.approver", trimmedApprover);
      const response = await api.decide(run.run_id, {
        decision,
        approver: trimmedApprover,
        reason: trimmedReason,
      });
      onDecided(response);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : String(caught),
      );
    } finally {
      setPending(null);
    }
  }

  if (decided) {
    return <DecisionOutcome run={run} />;
  }

  return (
    <Panel
      label="Human approval"
      hint="the graph is suspended at interrupt() until this is answered"
      tone="critical"
      right={
        <StatusTag tone="critical" glyph="&#9995;">
          Awaiting decision
        </StatusTag>
      }
    >
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex flex-col gap-3">
          <label className="block">
            <span className="u-label">Acting approver (your identity)</span>
            <input
              value={approver}
              onChange={(event) => setApprover(event.target.value)}
              placeholder="e.g. j.okafor"
              autoComplete="off"
              spellCheck={false}
              className="mt-1 w-full border px-2 py-1.5"
              style={{
                ...inputStyle,
                fontFamily: "var(--mono)",
                borderColor: sameActor ? "var(--ink-critical)" : "var(--rule-strong)",
              }}
            />
          </label>
          <div className="flex flex-col gap-1">
            <span className="u-label">Proposed by (server-assigned)</span>
            <Key>{run.proposed_by}</Key>
          </div>
          {sameActor ? (
            <p style={{ color: "var(--ink-critical)", fontSize: "13px", lineHeight: 1.5 }}>
              Segregation of duties: the approver must differ from the proposer.
              `record_approved_resolution` rejects a write where these match.
            </p>
          ) : (
            <p className="u-label" style={{ lineHeight: 1.6 }}>
              Recorded on the memory write. Must differ from the proposer, which
              is why it is not a fixed string.
            </p>
          )}
        </div>

        <label className="block">
          <span className="u-label">Reason (recorded with the decision)</span>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={5}
            placeholder="What you checked, and why this disposition is right."
            className="mt-1 w-full border px-2 py-1.5"
            style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6 }}
          />
        </label>
      </div>

      {error ? (
        <p
          className="mt-3 border px-2 py-1.5"
          style={{
            borderColor: "var(--border-critical)",
            color: "var(--ink-critical)",
            fontSize: "13px",
          }}
        >
          {error}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button
          tone="good"
          variant="primary"
          disabled={!ready || pending !== null}
          onClick={() => submit("approve")}
        >
          {pending === "approve" ? "Resuming…" : "Approve proposal"}
        </Button>
        <Button
          tone="critical"
          disabled={!ready || pending !== null}
          onClick={() => submit("reject")}
        >
          {pending === "reject" ? "Resuming…" : "Reject"}
        </Button>
        <p className="u-label" style={{ flex: 1, minWidth: "18rem", lineHeight: 1.6 }}>
          Approving resumes the graph and writes one episodic record to this
          supplier&rsquo;s memory namespace. It does not post, pay or release
          anything &mdash; no such path exists. Rejecting resumes the graph too,
          and writes nothing.
        </p>
      </div>
    </Panel>
  );
}

function DecisionOutcome({ run }: { run: RunView }) {
  const decision = run.decision;
  const approved = run.status === "approved";
  return (
    <Panel
      label="Decision recorded"
      hint={`run ${run.run_id}`}
      right={
        approved ? (
          <StatusTag tone="good" glyph="&#10003;">
            Approved
          </StatusTag>
        ) : (
          <StatusTag tone="critical" glyph="&#10007;">
            Rejected
          </StatusTag>
        )
      }
    >
      <dl className="grid gap-x-6 gap-y-2 md:grid-cols-3">
        <div>
          <dt className="u-label">Approver</dt>
          <dd className="mt-0.5">
            <Key>{decision?.approver ?? "—"}</Key>
          </dd>
        </div>
        <div>
          <dt className="u-label">Proposer</dt>
          <dd className="mt-0.5">
            <Key>{decision?.proposed_by ?? run.proposed_by}</Key>
          </dd>
        </div>
        <div>
          <dt className="u-label">Memory write</dt>
          <dd className="mt-0.5">
            {decision?.memory_written ? (
              <StatusTag tone="good" glyph="&#10003;">
                One episodic record
              </StatusTag>
            ) : (
              <StatusTag tone="neutral" glyph="&#8709;">
                Nothing written
              </StatusTag>
            )}
          </dd>
        </div>
      </dl>
      <div className="mt-3">
        <p className="u-label">Reason given</p>
        <p style={{ color: "var(--ink)", fontSize: "13.5px", lineHeight: 1.6 }}>
          {decision?.reason}
        </p>
      </div>
      {!approved ? (
        <p className="u-label mt-3" style={{ lineHeight: 1.6 }}>
          The approval layer refused the write before touching the store:{" "}
          {decision?.detail ?? "resolution memory cannot be written without approval"}.
          A rejection is a terminal outcome for this run, not an error.
        </p>
      ) : null}
    </Panel>
  );
}

export function SupplierMemoryPanel({
  supplier,
  records,
}: {
  supplier: string;
  records: MemoryRecord[];
}) {
  return (
    <Panel
      label="Supplier memory"
      hint={`namespace ${supplier}`}
      right={
        <StatusTag tone={records.length ? "good" : "neutral"} glyph={records.length ? "●" : "○"}>
          {records.length} record(s)
        </StatusTag>
      }
    >
      {records.length === 0 ? (
        <p className="u-label" style={{ lineHeight: 1.6 }}>
          Nothing written for this supplier. Long-term writes happen only after
          a human approves a resolution, so a wrong call on one case cannot
          poison a later one.
        </p>
      ) : (
        <ul className="flex flex-col gap-px" style={{ background: "var(--rule)" }}>
          {records.map((record, index) => (
            <li key={index} className="px-2 py-1.5" style={{ background: "var(--surface)" }}>
              <div className="flex flex-wrap items-center gap-2">
                <StatusTag tone="info" glyph="◆">
                  {record.kind}
                </StatusTag>
                <Key>
                  {record.case_purchase_order}/{record.case_purchase_order_item}
                </Key>
                <span className="u-label">approved by {record.approved_by}</span>
              </div>
              <p
                className="mt-1"
                style={{ color: "var(--ink-2)", fontSize: "13px", lineHeight: 1.5 }}
              >
                {record.text}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
