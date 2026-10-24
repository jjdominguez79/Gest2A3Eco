/// Estado legacy de una factura online (se conserva por compatibilidad; las
/// pantallas nuevas deben preferir los estados separados de
/// [InvoiceLifecycleStatus], [FiscalStatus], [PdfStatus], [DeliveryStatus] y
/// [AccountingSyncStatus], que nunca mezclan emision, PDF, email, AEAT y
/// contabilidad en una unica senal).
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

/// Ciclo de vida principal de la factura (campo `invoice_status`). Nunca
/// vuelve a `draft` por un error tecnico de PDF/email/contabilidad.
enum InvoiceLifecycleStatus {
  draft('Borrador'),
  issued('Emitida'),
  cancelled('Anulada'),
  rectified('Rectificada');

  const InvoiceLifecycleStatus(this.label);
  final String label;

  static InvoiceLifecycleStatus fromString(String value) {
    switch (value) {
      case 'issued':
        return InvoiceLifecycleStatus.issued;
      case 'cancelled':
        return InvoiceLifecycleStatus.cancelled;
      case 'rectified':
        return InvoiceLifecycleStatus.rectified;
      default:
        return InvoiceLifecycleStatus.draft;
    }
  }
}

/// Estado del registro fiscal Veri*FACTU (campo `fiscal_status`).
enum FiscalStatus {
  pending('Pendiente de envio'),
  processing('Enviando a la AEAT'),
  sent('Enviado a la AEAT'),
  accepted('Aceptado por la AEAT'),
  rejected('Rechazado por la AEAT'),
  incident('Incidencia fiscal');

  const FiscalStatus(this.label);
  final String label;

  static FiscalStatus fromString(String value) {
    switch (value) {
      case 'processing':
        return FiscalStatus.processing;
      case 'sent':
        return FiscalStatus.sent;
      case 'accepted':
        return FiscalStatus.accepted;
      case 'rejected':
        return FiscalStatus.rejected;
      case 'incident':
        return FiscalStatus.incident;
      default:
        return FiscalStatus.pending;
    }
  }

  bool get isProblem => this == FiscalStatus.rejected || this == FiscalStatus.incident;
}

/// Estado de generacion del PDF (campo `pdf_status`).
enum PdfStatus {
  pending('Pendiente de generar'),
  processing('Generando'),
  generated('Generado'),
  error('Error al generar');

  const PdfStatus(this.label);
  final String label;

  static PdfStatus fromString(String value) {
    switch (value) {
      case 'processing':
        return PdfStatus.processing;
      case 'generated':
        return PdfStatus.generated;
      case 'error':
        return PdfStatus.error;
      default:
        return PdfStatus.pending;
    }
  }
}

/// Estado de entrega por email/notificacion (campo `delivery_status`).
enum DeliveryStatus {
  pending('Pendiente de enviar'),
  sending('Enviando'),
  sent('Enviado'),
  skipped('Omitido (sin destinatario)'),
  error('Error al enviar'),
  uncertain('Estado incierto');

  const DeliveryStatus(this.label);
  final String label;

  static DeliveryStatus fromString(String value) {
    switch (value) {
      case 'sending':
        return DeliveryStatus.sending;
      case 'sent':
        return DeliveryStatus.sent;
      case 'skipped':
        return DeliveryStatus.skipped;
      case 'error':
        return DeliveryStatus.error;
      case 'uncertain':
        return DeliveryStatus.uncertain;
      default:
        return DeliveryStatus.pending;
    }
  }
}

/// Estado de la importacion contable al escritorio (campo
/// `accounting_sync_status`). Un problema aqui nunca afecta a la validez
/// fiscal de la factura.
enum AccountingSyncStatus {
  pending('Pendiente de contabilizar'),
  processing('Contabilizando'),
  imported('Contabilizada'),
  reviewRequired('Requiere revision de Gestinem'),
  error('Error al contabilizar');

  const AccountingSyncStatus(this.label);
  final String label;

  static AccountingSyncStatus fromString(String value) {
    switch (value) {
      case 'processing':
        return AccountingSyncStatus.processing;
      case 'imported':
        return AccountingSyncStatus.imported;
      case 'review_required':
        return AccountingSyncStatus.reviewRequired;
      case 'error':
        return AccountingSyncStatus.error;
      default:
        return AccountingSyncStatus.pending;
    }
  }
}

/// Origen de la factura: creada desde Flutter o importada desde el
/// escritorio (solo lectura en Flutter).
enum InvoiceSourceSystem {
  clientApp('App'),
  desktop('Escritorio');

  const InvoiceSourceSystem(this.label);
  final String label;

  static InvoiceSourceSystem fromString(String value) {
    return value == 'desktop'
        ? InvoiceSourceSystem.desktop
        : InvoiceSourceSystem.clientApp;
  }
}
