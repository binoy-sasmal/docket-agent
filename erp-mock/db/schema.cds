// Docket's four read entities, with the field names and types of
// docket.schema.procurement. Seeded at startup from db/data/*.csv, which
// tools/export_erp_mock_data.py generates from the frozen fixtures.
//
// Decimal scales mirror the fixtures exactly: every net price has one
// decimal place and every document amount two, and the largest value has
// seven digits. Docket's claim text prints an amount at the scale its source
// supplies, so a different scale here would change the wording of a proposal
// (never its decision) between connected and frozen mode.
namespace docket.erp;

type ActingUser {
  user_id       : String;
  is_batch_user : Boolean;
}

entity PurchaseOrders {
  key PurchaseOrder          : String(10);
      CompanyCode            : String;
      PurchaseOrderType      : String;
      Supplier               : String;
      PurchasingOrganization : String;
      PurchasingGroup        : String;
      DocumentCurrency       : String(5);
      PurchaseOrderDate      : DateTime;
      CreatedByUser          : ActingUser;
}

entity PurchaseOrderItems {
  key PurchaseOrder              : String(10);
  key PurchaseOrderItem          : String(5);
      Material                   : String;
      MaterialGroup              : String;
      Plant                      : String;
      OrderQuantity              : Decimal(15, 3);
      PurchaseOrderQuantityUnit  : String;
      NetPriceAmount             : Decimal(15, 1);
      DocumentCurrency           : String(5);
      GoodsReceiptIsExpected     : Boolean;
      InvoiceIsGoodsReceiptBased : Boolean;
      IsCompletelyDelivered      : Boolean;
      IsFinallyInvoiced          : Boolean;
      PurchaseOrderItemCategory  : String;
      AccountAssignmentCategory  : String;
      Note                       : String;
}

entity MaterialDocumentItems {
  key MaterialDocumentYear     : String(4);
  key MaterialDocument         : String;
  key MaterialDocumentItem     : String(4);
      GoodsMovementType        : String(3);
      DocumentDate             : DateTime;
      PostingDate              : DateTime;
      CreatedByUser            : ActingUser;
      PurchaseOrder            : String(10);
      PurchaseOrderItem        : String(5);
      QuantityInEntryUnit      : Decimal(15, 3);
      EntryUnit                : String;
      Plant                    : String;
      ReversesMaterialDocument : String;
      Amount                   : Decimal(15, 2);
      AmountProvenance         : String;
      Note                     : String;
}

entity SupplierInvoiceItems {
  key SupplierInvoice               : String;
  key FiscalYear                    : String(4);
  key SupplierInvoiceItem           : String;
      CompanyCode                   : String;
      DocumentDate                  : DateTime;
      PostingDate                   : DateTime;
      InvoicingParty                : String;
      SupplierInvoiceIDByInvcgParty : String;
      PurchaseOrder                 : String(10);
      PurchaseOrderItem             : String(5);
      QuantityInPurchaseOrderUnit   : Decimal(15, 3);
      SupplierInvoiceItemAmount     : Decimal(15, 2);
      AmountProvenance              : String;
      DocumentCurrency              : String(5);
      PaymentTerms                  : String;
      ReverseDocument               : String;
      ReferencesMaterialDocument    : String;
      Note                          : String;
}
