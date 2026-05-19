from datetime import date

from core.models import ExtractionResult, InvoiceRecord, TenantConfig, ValidationIssue, ValidationResult


def validate(
    record: InvoiceRecord,
    result: ExtractionResult,
    tenant_config: TenantConfig,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    def val(field_name: str):
        fv = result.fields.get(field_name)
        return fv.value if fv else None

    def conf(field_name: str) -> float:
        fv = result.fields.get(field_name)
        return fv.confidence if fv else 0.0

    # Required fields present and non-null
    for f in tenant_config.required_fields:
        v = val(f)
        if v is None or v == "":
            issues.append(ValidationIssue(field=f, reason="Veld ontbreekt of is null", severity="error"))

    # Confidence below threshold
    threshold = tenant_config.confidence_threshold
    for f in tenant_config.required_fields:
        c = conf(f)
        if c < threshold and val(f) is not None:
            issues.append(ValidationIssue(
                field=f,
                reason=f"Confidence {c:.2f} < drempel {threshold:.2f}",
                severity="warning",
            ))

    # Arithmetic consistency: net + vat ≈ gross (tolerance 0.02)
    gross = val("amount_gross")
    net = val("amount_net")
    vat = val("amount_vat")
    if gross is not None and net is not None and vat is not None:
        if abs(float(net) + float(vat) - float(gross)) > 0.02:
            issues.append(ValidationIssue(
                field="amount_gross",
                reason=f"Rekenkundige inconsistentie: net({net}) + vat({vat}) ≠ gross({gross})",
                severity="warning",
            ))

    # Invoice date not in the future
    invoice_date_str = val("invoice_date")
    if invoice_date_str:
        try:
            invoice_date = date.fromisoformat(str(invoice_date_str))
            if invoice_date > date.today():
                issues.append(ValidationIssue(
                    field="invoice_date",
                    reason=f"Factuurdatum {invoice_date_str} ligt in de toekomst",
                    severity="warning",
                ))
        except ValueError:
            issues.append(ValidationIssue(
                field="invoice_date",
                reason=f"Ongeldige datumnotatie: {invoice_date_str}",
                severity="error",
            ))

    has_errors = any(i.severity == "error" for i in issues)
    return ValidationResult(ok=not has_errors, issues=issues)
