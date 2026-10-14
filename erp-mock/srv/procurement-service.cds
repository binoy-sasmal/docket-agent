// The four entity sets Docket's Investigator may read, named as in SAP's
// procurement APIs. Every entity is @readonly: CAP rejects create, update and
// delete with 405, so this service has no write path, matching Docket's
// claim that the agent cannot post.
using docket.erp as db from '../db/schema';

service ProcurementService @(path: '/odata/v4/procurement') {
  @readonly entity A_PurchaseOrder                as projection on db.PurchaseOrders;
  @readonly entity A_PurchaseOrderItem            as projection on db.PurchaseOrderItems;
  @readonly entity A_MaterialDocumentItem         as projection on db.MaterialDocumentItems;
  @readonly entity A_SupplierInvoiceItemPurOrdRef as projection on db.SupplierInvoiceItems;
}
