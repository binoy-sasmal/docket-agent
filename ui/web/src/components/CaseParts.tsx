import type {
  ClaimView,
  Disposition,
  InvestigationView,
  Meta,
  PolicyView,
  ProposalView,
  ReconciliationView,
  RunView,
} from "../api";
import { Empty, Field, Key, Panel, StatusTag } from "./primitives";

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  post: "Post",
  hold: "Hold",
  request_credit_memo: "Request credit memo",
  escalate: "Escalate",
  route: "Route",
};

/**
 * Disposition colour is deliberately NOT a five-hue categorical scale.
 * These are outcome states, so they wear status tokens: "post" is the only
 * clean outcome, the rest each demand a different kind of human attention.
 * Every use pairs the colour with the written disposition, never colour alone.
 */
export const DISPOSITION_TONE: Record<
  Disposition,
  "good" | "warning" | "serious" | "critical" | "info"
> = {
  post: "good",
  hold: "warning",
  request_credit_memo: "serious",
  escalate: "critical",
  route: "info",
};

export const DISPOSITION_GLYPH: Record<Disposition, string> = {
  post: "●",
  hold: "■",
  request_credit_memo: "◆",
  escalate: "▲",
  route: "▶",
};

export function DispositionTag({ disposition }: { disposition: Disposition }) {
  return (
    <StatusTag tone={DISPOSITION_TONE[disposition]} glyph={DISPOSITION_GLYPH[disposition]}>
      {DISPOSITION_LABEL[disposition]}
    </StatusTag>
  );
}

/* --- Stage rail ---------------------------------------------------------- */

const STAGES = ["Investigator", "Reconciler", "Policy gate", "Proposer"] as const;

/**
 * The four nodes plus the approval gate, rendered from the server's copy of
 * the docs/PROJECT.md 3.1 permission matrix.
 *
 * This is the security argument, not decoration: the reader should be able to
 * see that untrusted text enters at one node, that the next node holds no
 * tools, and that the gate that picks the disposition runs no model.
 */
export function StageRail({ matrix }: { matrix: Meta["node_matrix"] }) {
  const byNode = new Map(matrix.map((row) => [row.node, row]));
  return (
    <div className="u-card u-scroll-x">
      <div className="grid min-w-[860px] grid-cols-5 divide-x" style={{ borderColor: "var(--rule)" }}>
        {STAGES.map((stage, index) => {
          const row = byNode.get(stage);
          return (
            <div
              key={stage}
              className="p-3"
              style={{ background: "var(--surface)", borderColor: "var(--rule)" }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex items-center justify-center"
                  style={{
                    width: "20px",
                    height: "20px",
                    borderRadius: "999px",
                    background: "var(--surface-3)",
                    color: "var(--ink-2)",
                    fontSize: "11px",
                    fontWeight: 600,
                  }}
                >
                  {index + 1}
                </span>
                <h3 className="u-display" style={{ fontSize: "15px", color: "var(--ink)" }}>
                  {stage}
                </h3>
              </div>
              <dl className="mt-2 flex flex-col gap-1">
                <div className="flex items-center gap-1.5">
                  <dt className="u-label">Tools</dt>
                  <dd style={{ fontSize: "12.5px", color: "var(--ink-2)" }}>
                    {row?.tools ?? "—"}
                  </dd>
                </div>
                <div className="flex items-center gap-1.5">
                  <dt className="u-label">Model</dt>
                  <dd>
                    {row ? (
                      row.model ? (
                        <StatusTag tone="info" glyph="●">
                          Yes
                        </StatusTag>
                      ) : (
                        <StatusTag tone="good" glyph="⊘" title={row.rationale}>
                          None ever
                        </StatusTag>
                      )
                    ) : (
                      "—"
                    )}
                  </dd>
                </div>
              </dl>
              <p
                className="mt-2"
                style={{ fontSize: "12.5px", lineHeight: 1.5, color: "var(--ink-muted)" }}
              >
                {row?.rationale}
              </p>
            </div>
          );
        })}
        <div
          className="p-3"
          style={{ background: "var(--tint-critical)", borderColor: "var(--rule)" }}
        >
          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center justify-center"
              style={{
                width: "20px",
                height: "20px",
                borderRadius: "999px",
                background: "var(--border-critical)",
                color: "var(--ink-critical)",
                fontSize: "11px",
                fontWeight: 600,
              }}
            >
              5
            </span>
            <h3 className="u-display" style={{ fontSize: "15px", color: "var(--ink-critical)" }}>
              Approval
            </h3>
          </div>
          <div className="mt-2.5">
            <StatusTag tone="critical" glyph="&#9995;">
              interrupt()
            </StatusTag>
          </div>
          <p
            className="mt-2"
            style={{ fontSize: "12.5px", lineHeight: 1.5, color: "var(--ink-muted)" }}
          >
            A real LangGraph interrupt. The graph is suspended here and cannot
            continue without a human resuming it.
          </p>
        </div>
      </div>
    </div>
  );
}

/* --- Trajectory ---------------------------------------------------------- */

export function TrajectoryPanel({ investigation }: { investigation: InvestigationView }) {
  return (
    <Panel
      label="Investigation trajectory"
      hint={`${investigation.tool_calls.length} read-only tool call(s), in order`}
    >
      <ol className="flex flex-col gap-px" style={{ background: "var(--rule)" }}>
        {investigation.tool_calls.map((call) => (
          <li
            key={`${call.sequence}-${call.name}`}
            className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 px-3 py-2"
            style={{ background: "var(--surface)" }}
          >
            <span
              className="u-tabular shrink-0"
              style={{ color: "var(--ink-muted)", fontSize: "12.5px" }}
            >
              {String(call.sequence).padStart(2, "0")}
            </span>
            {/* --ink-link, not the chart hue: --series-1 measures 4.4:1 on
                white, which clears the 3:1 mark floor but not 4.5:1 for text. */}
            <code
              style={{
                color: "var(--ink-link)",
                fontFamily: "var(--mono)",
                fontSize: "13px",
                fontWeight: 500,
              }}
            >
              {call.name}
            </code>
            <span className="flex flex-wrap gap-x-2 gap-y-0.5">
              {Object.entries(call.arguments).map(([name, value]) => (
                <span key={name} className="u-label">
                  {name}=
                  <span style={{ color: "var(--ink-2)", fontFamily: "var(--mono)" }}>{value}</span>
                </span>
              ))}
            </span>
          </li>
        ))}
      </ol>
      <p className="u-label mt-2" style={{ lineHeight: 1.6 }}>
        Recorded by the tool facade itself, in call order &mdash; not
        reconstructed from what the agent said it did. This sequence is what
        trajectory correctness is scored against.
      </p>
    </Panel>
  );
}

/* --- Claims and evidence ------------------------------------------------- */

const EVIDENCE_KIND_LABEL: Record<string, string> = {
  purchase_order_item: "PO ITEM",
  material_document: "GOODS RECEIPT",
  supplier_invoice: "INVOICE",
};

export function ClaimsPanel({
  claims,
  narrative,
  selectedKey,
  onSelectKey,
}: {
  claims: ClaimView[];
  narrative: string | null;
  selectedKey: string | null;
  onSelectKey: (key: string | null) => void;
}) {
  const ungrounded = claims.filter((claim) => !claim.grounded).length;
  return (
    <Panel
      label="Reconciliation claims"
      hint="every claim carries a document key"
      right={
        ungrounded > 0 ? (
          <StatusTag tone="critical" glyph="&#9888;">
            {ungrounded} ungrounded
          </StatusTag>
        ) : (
          <StatusTag tone="good" glyph="&#10003;">
            All grounded
          </StatusTag>
        )
      }
    >
      <ul className="flex flex-col gap-px" style={{ background: "var(--rule)" }}>
        {claims.map((claim, index) => (
          <li
            key={`${index}-${claim.text}`}
            className="px-2 py-2"
            style={{ background: "var(--surface)" }}
          >
            <div className="flex items-start gap-2">
              <span
                className="u-tabular shrink-0"
                style={{ color: "var(--ink-muted)", fontSize: "12.5px", paddingTop: "1px" }}
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <p style={{ color: "var(--ink)", fontSize: "13.5px", lineHeight: 1.5 }}>
                {claim.text}
              </p>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 pl-6">
              {claim.evidence.length === 0 ? (
                <StatusTag tone="critical" glyph="&#9888;">
                  No evidence handle
                </StatusTag>
              ) : (
                claim.evidence.map((handle) => {
                  const active = selectedKey === handle.key;
                  return (
                    <button
                      key={`${handle.kind}:${handle.key}`}
                      type="button"
                      onClick={() => onSelectKey(active ? null : handle.key)}
                      className="flex items-center gap-1.5 border px-1.5 py-0.5"
                      title={`Highlight ${handle.key} in the documents below`}
                      style={{
                        borderColor: active ? "var(--series-1)" : "var(--rule-strong)",
                        background: active ? "var(--tint-info)" : "var(--surface-3)",
                        cursor: "pointer",
                      }}
                    >
                      <span className="u-label" style={{ letterSpacing: "0.1em" }}>
                        {EVIDENCE_KIND_LABEL[handle.kind] ?? handle.kind}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: "12.5px",
                          color: "var(--ink)",
                        }}
                      >
                        {handle.key}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </li>
        ))}
      </ul>
      {narrative ? (
        <div className="mt-3 border-t pt-2" style={{ borderColor: "var(--rule)" }}>
          <p className="u-label">Model-authored narrative (tool-free node)</p>
          <p
            className="mt-1"
            style={{ color: "var(--ink-2)", fontSize: "13.5px", lineHeight: 1.6 }}
          >
            {narrative}
          </p>
        </div>
      ) : null}
      <p className="u-label mt-2" style={{ lineHeight: 1.6 }}>
        Select a key to locate that document below. Claims and their handles are
        derived in code from the documents actually fetched, not written by the
        model.
      </p>
    </Panel>
  );
}

/* --- Policy -------------------------------------------------------------- */

function AmountRow({
  label,
  value,
  currency,
  emphasis = false,
}: {
  label: string;
  value: string | null;
  currency: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className="flex items-baseline justify-between gap-3 border-b py-1"
      style={{ borderColor: "var(--rule)" }}
    >
      <span className="u-label">{label}</span>
      <span
        className="u-tabular"
        style={{
          color: value === null ? "var(--ink-muted)" : "var(--ink)",
          fontSize: emphasis ? "14px" : "12.5px",
          fontWeight: emphasis ? 600 : 400,
        }}
      >
        {value === null ? "n/a" : `${value} ${currency}`}
      </span>
    </div>
  );
}

export function PolicyPanel({
  policy,
  reconciliation,
  currency,
  tolerancePolicy,
}: {
  policy: PolicyView;
  reconciliation: ReconciliationView;
  currency: string;
  tolerancePolicy: Meta["tolerance_policy"];
}) {
  return (
    <Panel
      label="Policy gate"
      hint="deterministic Python — no model in this node"
      right={
        policy.within_tolerance ? (
          <StatusTag tone="good" glyph="&#10003;">
            Within tolerance
          </StatusTag>
        ) : (
          <StatusTag tone="warning" glyph="&#9888;">
            Outside tolerance
          </StatusTag>
        )
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="u-label mb-1">Amounts compared</p>
          <AmountRow
            label="PO item net"
            value={reconciliation.purchase_order_amount}
            currency={currency}
          />
          <AmountRow
            label={`Goods receipts (${reconciliation.goods_receipt_count})`}
            value={reconciliation.goods_receipt_amount}
            currency={currency}
          />
          <AmountRow
            label={`Invoices (${reconciliation.invoice_count})`}
            value={reconciliation.invoice_amount}
            currency={currency}
          />
          <AmountRow
            label="GR variance"
            value={reconciliation.goods_receipt_variance}
            currency={currency}
          />
          <AmountRow
            label="Invoice variance"
            value={reconciliation.invoice_variance}
            currency={currency}
          />
        </div>
        <div>
          <p className="u-label mb-1">Threshold test</p>
          <AmountRow
            label="Max abs variance"
            value={policy.max_abs_variance}
            currency={currency}
            emphasis
          />
          <AmountRow
            label="Tolerance"
            value={policy.tolerance_amount}
            currency={currency}
            emphasis
          />
          <p className="u-label mt-2" style={{ lineHeight: 1.6 }}>
            Tolerance is the larger of an absolute floor of{" "}
            {tolerancePolicy.absolute_tolerance} {currency} and{" "}
            {tolerancePolicy.relative_tolerance_bps} bps (
            {(tolerancePolicy.relative_tolerance_bps / 100).toFixed(2)}%) of the
            PO amount.
          </p>
          <div className="mt-3 flex flex-col gap-2">
            <Field label="Reason code" value={<Key>{policy.reason}</Key>} />
            <div>
              <p className="u-label">Allowed dispositions</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {policy.allowed_dispositions.map((disposition) => (
                  <DispositionTag key={disposition} disposition={disposition} />
                ))}
              </div>
            </div>
            <Field
              label="Item category"
              value={reconciliation.purchase_order_item_category}
              mono={false}
            />
          </div>
        </div>
      </div>
    </Panel>
  );
}

/* --- Proposal ------------------------------------------------------------ */

export function ProposalPanel({
  proposal,
  run,
  canPostNote,
}: {
  proposal: ProposalView;
  run: RunView;
  canPostNote: string;
}) {
  return (
    <Panel
      label="Proposal"
      hint={`proposed by ${run.proposed_by}`}
      right={<DispositionTag disposition={proposal.disposition} />}
    >
      <p style={{ color: "var(--ink)", fontSize: "14px", lineHeight: 1.6 }}>
        {proposal.summary}
      </p>
      <div
        className="mt-3 flex flex-wrap items-center gap-2 border px-2 py-2"
        style={{ borderColor: "var(--rule-strong)", background: "var(--surface-2)" }}
      >
        <StatusTag tone="good" glyph="&#128274;">
          can_post = false
        </StatusTag>
        <p className="u-label" style={{ flex: 1, minWidth: "16rem", lineHeight: 1.6 }}>
          {canPostNote}
        </p>
      </div>
    </Panel>
  );
}

/* --- Documents ----------------------------------------------------------- */

function DocTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: { key: string; highlighted: boolean; cells: React.ReactNode[] }[];
}) {
  return (
    <div className="u-scroll-x">
      <table className="w-full border-collapse" style={{ fontSize: "13px" }}>
        <thead>
          <tr>
            {columns.map((column) => (
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
          {rows.map((row) => (
            <tr
              key={row.key}
              style={{
                background: row.highlighted ? "var(--tint-info)" : "transparent",
                outline: row.highlighted ? "1px solid var(--series-1)" : "none",
              }}
            >
              {row.cells.map((cell, index) => (
                <td
                  key={index}
                  className="u-tabular border-b px-2 py-1"
                  style={{ borderColor: "var(--rule)", whiteSpace: "nowrap" }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const shortDate = (iso: string) => iso.slice(0, 10);

export function DocumentsPanel({
  investigation,
  selectedKey,
}: {
  investigation: InvestigationView;
  selectedKey: string | null;
}) {
  const item = investigation.purchase_order_item;
  const order = investigation.purchase_order;
  const itemKey = investigation.purchase_order_item_key;

  return (
    <Panel label="Documents read" hint="the evidence the claims point at">
      <div
        className="border p-2"
        style={{
          borderColor: selectedKey === itemKey ? "var(--series-1)" : "var(--rule)",
          background: selectedKey === itemKey ? "var(--tint-info)" : "var(--surface-2)",
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="u-label-ink">A_PurchaseOrder / A_PurchaseOrderItem</span>
          <Key>{itemKey}</Key>
        </div>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-4">
          <Field label="Supplier" value={order.Supplier} />
          <Field label="Company code" value={order.CompanyCode} />
          <Field label="PO type" value={order.PurchaseOrderType} />
          <Field label="PO date" value={shortDate(order.PurchaseOrderDate)} />
          <Field
            label="Net price amount"
            value={`${item.NetPriceAmount} ${item.DocumentCurrency}`}
          />
          <Field label="GR expected" value={item.GoodsReceiptIsExpected ? "true" : "false"} />
          <Field label="GR-based invoicing" value={item.InvoiceIsGoodsReceiptBased ? "true" : "false"} />
          <Field
            label="Created by"
            value={`${order.CreatedByUser.user_id}${order.CreatedByUser.is_batch_user ? " (batch)" : ""}`}
          />
        </dl>
        <div className="mt-2">
          <Field label="Item category" value={item.PurchaseOrderItemCategory} mono={false} />
        </div>
      </div>

      <div className="mt-3">
        <p className="u-label mb-1">
          A_MaterialDocumentItem &mdash; goods receipts ({investigation.goods_receipts.length})
        </p>
        {investigation.goods_receipts.length === 0 ? (
          <Empty>
            {item.GoodsReceiptIsExpected
              ? "None found. The document class was queried and returned nothing — affirmative negative evidence."
              : "Not expected for this item; the class was not queried."}
          </Empty>
        ) : (
          <DocTable
            columns={["Key", "Movement", "Posting date", "Amount", "Reverses", "By"]}
            rows={investigation.goods_receipts.map((receipt) => {
              const key = `${receipt.MaterialDocument}/${receipt.MaterialDocumentItem}`;
              return {
                key,
                highlighted: selectedKey === key,
                cells: [
                  <Key>{key}</Key>,
                  receipt.GoodsMovementType === "102" ? (
                    <StatusTag tone="warning" glyph="&#8630;">
                      102 reversal
                    </StatusTag>
                  ) : (
                    <span style={{ color: "var(--ink-2)" }}>101 receipt</span>
                  ),
                  shortDate(receipt.PostingDate),
                  receipt.Amount,
                  receipt.ReversesMaterialDocument ?? "—",
                  `${receipt.CreatedByUser.user_id}${receipt.CreatedByUser.is_batch_user ? " (batch)" : ""}`,
                ],
              };
            })}
          />
        )}
      </div>

      <div className="mt-3">
        <p className="u-label mb-1">
          A_SupplierInvoiceItemPurOrdRef &mdash; invoices ({investigation.invoices.length})
        </p>
        {investigation.invoices.length === 0 ? (
          <Empty>
            None found. The document class was queried and returned nothing
            &mdash; affirmative negative evidence.
          </Empty>
        ) : (
          <DocTable
            columns={["Key", "Supplier ref", "Posting date", "Amount", "Reverses"]}
            rows={investigation.invoices.map((invoice) => {
              const key = `${invoice.SupplierInvoice}/${invoice.SupplierInvoiceItem}`;
              return {
                key,
                highlighted: selectedKey === key,
                cells: [
                  <Key>{key}</Key>,
                  invoice.SupplierInvoiceIDByInvcgParty,
                  shortDate(invoice.PostingDate),
                  `${invoice.SupplierInvoiceItemAmount} ${invoice.DocumentCurrency}`,
                  invoice.ReverseDocument ?? "—",
                ],
              };
            })}
          />
        )}
      </div>
    </Panel>
  );
}
