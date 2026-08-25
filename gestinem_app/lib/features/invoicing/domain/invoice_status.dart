/// Estados de una factura online.
enum InvoiceStatus {
  draft('Borrador'),
  issuedPendingProcessing('Emitida - Pendiente'),
  claimed('En proceso'),
  imported('Importada'),
  rendered('PDF generado'),
  emailed('Email enviado'),
  processingError('Error'),
  cancelled('Anulada'),
  replaced('Sustituida');

  const InvoiceStatus(this.label);
  final String label;

  static InvoiceStatus fromString(String value) {
    switch (value) {
      case 'draft':
        return InvoiceStatus.draft;
      case 'issued_pending_processing':
        return InvoiceStatus.issuedPendingProcessing;
      case 'claimed':
        return InvoiceStatus.claimed;
      case 'imported':
        return InvoiceStatus.imported;
      case 'rendered':
        return InvoiceStatus.rendered;
      case 'emailed':
        return InvoiceStatus.emailed;
      case 'processing_error':
        return InvoiceStatus.processingError;
      case 'cancelled':
        return InvoiceStatus.cancelled;
      case 'replaced':
        return InvoiceStatus.replaced;
      default:
        return InvoiceStatus.draft;
    }
  }

  bool get isDraft => this == InvoiceStatus.draft;
  bool get isProcessing =>
      this == InvoiceStatus.issuedPendingProcessing ||
      this == InvoiceStatus.claimed ||
      this == InvoiceStatus.imported;
  bool get isComplete =>
      this == InvoiceStatus.rendered || this == InvoiceStatus.emailed;
  bool get isError => this == InvoiceStatus.processingError;
}
