/**
 * Typed client for the Docket API.
 *
 * Every monetary field is `string`, never `number`. The backend stringifies
 * Decimal on purpose -- a JSON number round-trips through float in JavaScript,
 * which is exactly the precision loss the project's canonical serialiser
 * refuses to accept. These values are displayed, never arithmetic'd, here.
 */

export type RunMode = "deterministic" | "live";
export type RunStatus = "awaiting_approval" | "approved" | "rejected";
export type Disposition =
  | "post"
  | "hold"
  | "request_credit_memo"
  | "escalate"
  | "route";

export interface NodeMatrixRow {
  node: string;
  tools: string;
  model: boolean;
  rationale: string;
}

export interface PublicOverlay {
  overlay_id: string;
  case_id: string;
  target: string;
  payload: string;
  success_condition: string;
}

export interface HeldOutOverlay {
  overlay_id: string;
  case_id: string;
  target: string;
  authored: boolean;
  success_condition: string;
}

export interface GoldenSetMeta {
  label_count: number;
  labels_status: string;
  flagged_injection_cases: number;
  public_overlay_count: number;
  held_out_overlay_count: number;
  held_out_authored_count: number;
  public_overlays: PublicOverlay[];
  held_out_overlays: HeldOutOverlay[];
}

export interface Meta {
  can_post: boolean;
  can_post_note: string;
  persistence_note: string;
  live_mode_available: boolean;
  live_model: string;
  node_matrix: NodeMatrixRow[];
  tolerance_policy: {
    absolute_tolerance: string;
    relative_tolerance_bps: number;
  };
  golden_set: GoldenSetMeta;
}

export interface CaseEntry {
  case_id: string;
  purchase_order: string;
  purchase_order_item: string;
  supplier: string;
  item_category: string;
  currency: string;
  purchase_order_amount: string;
  goods_receipt_count: number;
  invoice_count: number;
  goods_receipt_expected: boolean;
  in_golden_set: boolean;
  golden_disposition: Disposition | null;
  golden_reason_code: string | null;
  golden_is_injection_case: boolean;
  public_overlay_id: string | null;
}

export interface ToolCallView {
  sequence: number;
  name: string;
  arguments: Record<string, string>;
}

export interface EvidenceHandleView {
  kind: "purchase_order_item" | "material_document" | "supplier_invoice";
  key: string;
}

export interface ClaimView {
  text: string;
  evidence: EvidenceHandleView[];
  grounded: boolean;
}

/** Untrusted document free text. Rendered as quarantined data, never as UI. */
export interface UntrustedNote {
  source_kind: string;
  source_field: string;
  source_key: string;
  text: string;
}

export interface PurchaseOrderView {
  PurchaseOrder: string;
  CompanyCode: string;
  PurchaseOrderType: string;
  Supplier: string;
  DocumentCurrency: string;
  PurchaseOrderDate: string;
  CreatedByUser: { user_id: string; is_batch_user: boolean };
  [key: string]: unknown;
}

export interface PurchaseOrderItemView {
  PurchaseOrder: string;
  PurchaseOrderItem: string;
  NetPriceAmount: string;
  DocumentCurrency: string;
  GoodsReceiptIsExpected: boolean;
  InvoiceIsGoodsReceiptBased: boolean;
  PurchaseOrderItemCategory: string;
  Note: string | null;
  [key: string]: unknown;
}

export interface GoodsReceiptView {
  MaterialDocument: string;
  MaterialDocumentItem: string;
  GoodsMovementType: "101" | "102";
  PostingDate: string;
  Amount: string;
  ReversesMaterialDocument: string | null;
  CreatedByUser: { user_id: string; is_batch_user: boolean };
  Note: string | null;
  [key: string]: unknown;
}

export interface InvoiceView {
  SupplierInvoice: string;
  SupplierInvoiceItem: string;
  SupplierInvoiceIDByInvcgParty: string;
  PostingDate: string;
  SupplierInvoiceItemAmount: string;
  DocumentCurrency: string;
  ReverseDocument: string | null;
  Note: string | null;
  [key: string]: unknown;
}

export interface InvestigationView {
  case: { purchase_order: string; purchase_order_item: string };
  purchase_order: PurchaseOrderView;
  purchase_order_item: PurchaseOrderItemView;
  goods_receipts: GoodsReceiptView[];
  invoices: InvoiceView[];
  tool_calls: ToolCallView[];
  purchase_order_item_key: string;
  goods_receipt_keys: string[];
  invoice_keys: string[];
  untrusted_notes: UntrustedNote[];
}

export interface ReconciliationView {
  supplier: string;
  claims: ClaimView[];
  purchase_order_amount: string;
  goods_receipt_expected: boolean;
  goods_receipt_count: number;
  invoice_count: number;
  goods_receipt_amount: string | null;
  invoice_amount: string;
  goods_receipt_variance: string | null;
  invoice_variance: string;
  purchase_order_item_category: string;
  narrative: string | null;
}

export interface PolicyView {
  within_tolerance: boolean;
  reason: string;
  tolerance_amount: string;
  max_abs_variance: string;
  requires_human_approval: boolean;
  allowed_dispositions: Disposition[];
}

export interface ProposalView {
  disposition: Disposition;
  summary: string;
  supplier: string;
  claims: ClaimView[];
  policy: PolicyView;
  can_post: boolean;
}

export interface DecisionView {
  decision: "approve" | "reject";
  approver: string;
  reason: string;
  proposed_by: string;
  decided_at: string;
  memory_written: boolean;
  detail?: string;
}

export interface RunView {
  run_id: string;
  case_id: string;
  purchase_order: string;
  purchase_order_item: string;
  mode: RunMode;
  overlay_id: string | null;
  thread_id: string;
  proposed_by: string;
  status: RunStatus;
  created_at: string;
  decision: DecisionView | null;
  investigation: InvestigationView;
  reconciliation: ReconciliationView;
  policy: PolicyView;
  proposal: ProposalView;
  approval_request: { case_key: string; disposition: string; summary: string };
  interrupt_payload: Record<string, unknown>;
  golden: {
    in_golden_set: boolean;
    expected_disposition: Disposition | null;
    expected_reason_code: string | null;
    is_injection_case: boolean;
  };
}

export interface MemoryRecord {
  supplier: string;
  kind: string;
  case_purchase_order: string;
  case_purchase_order_item: string;
  text: string;
  approved_by: string;
}

export interface DecisionResponse {
  run: RunView;
  memory_record: MemoryRecord | null;
  supplier_memory: MemoryRecord[];
}

export interface CaseResultRow {
  case_id: string;
  expected_disposition: Disposition;
  actual_disposition: Disposition;
  disposition_correct: boolean;
  expected_reason: string;
  actual_reason: string;
  trajectory_correct: boolean;
  trajectory_gaps: string[];
  is_injection_case: boolean;
  injection_succeeded: boolean | null;
  citation_gaps: string[];
}

export interface EvalReportView {
  results: CaseResultRow[];
  disposition_accuracy: number;
  trajectory_accuracy: number;
  injection_success_rate: number | null;
  injection_cases_evaluated: number;
  used_model: boolean;
  case_count: number;
  computed_at: string;
}

export interface LiveEvalState {
  status: "idle" | "running" | "succeeded" | "failed";
  started_at: string | null;
  finished_at: string | null;
  report: EvalReportView | null;
  error: string | null;
  error_detail: string | null;
}

export interface EvalBundle {
  deterministic: EvalReportView;
  golden_set: GoldenSetMeta;
  live: LiveEvalState;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && body !== null
        ? ((body as { error?: string; detail?: unknown }).error ??
          JSON.stringify((body as { detail?: unknown }).detail ?? body))
        : text || response.statusText;
    throw new ApiError(String(detail), response.status);
  }
  return body as T;
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  cases: () =>
    request<{ count: number; golden_count: number; cases: CaseEntry[] }>(
      "/api/cases",
    ),
  createRun: (body: {
    purchase_order: string;
    purchase_order_item: string;
    mode: RunMode;
    overlay_id?: string | null;
  }) =>
    request<RunView>("/api/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  decide: (
    runId: string,
    body: { decision: "approve" | "reject"; approver: string; reason: string },
  ) =>
    request<DecisionResponse>(`/api/runs/${runId}/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  supplierMemory: (supplier: string) =>
    request<{ supplier: string; records: MemoryRecord[] }>(
      `/api/memory/${encodeURIComponent(supplier)}`,
    ),
  evalBundle: (refresh = false) =>
    request<EvalBundle>(`/api/eval${refresh ? "?refresh=true" : ""}`),
  liveEval: () => request<LiveEvalState>("/api/eval/live"),
  startLiveEval: () =>
    request<LiveEvalState>("/api/eval/live", { method: "POST" }),
};
