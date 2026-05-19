from datetime import date

from core.models import Concern, ExtractionResult, InvoiceRecord, TenantConfig, ValidationResult


def validate(
    record: InvoiceRecord,
    result: ExtractionResult,
    tenant_config: TenantConfig,
) -> ValidationResult:
    concerns: list[Concern] = []

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
            concerns.append(Concern(
                field=f,
                severity="blocking",
                reason="Verplicht veld ontbreekt of is null",
                suggested_next_steps=[f"Controleer of '{f}' leesbaar is op de factuur", "Escaleer naar leverancier als het veld ontbreekt"],
                source="validator",
            ))

    # Confidence below threshold
    threshold = tenant_config.confidence_threshold
    for f in tenant_config.required_fields:
        c = conf(f)
        if c < threshold and val(f) is not None:
            concerns.append(Concern(
                field=f,
                severity="warning",
                reason=f"Confidence {c:.2f} ligt onder de drempel {threshold:.2f}",
                suggested_next_steps=[f"Controleer veld '{f}' handmatig op de originele factuur"],
                source="validator",
            ))

    # Arithmetic consistency: net + vat ≈ gross (tolerance 0.02)
    gross = val("amount_gross")
    net = val("amount_net")
    vat = val("amount_vat")
    if gross is not None and net is not None and vat is not None:
        diff = abs(float(net) + float(vat) - float(gross))
        if diff > 0.02:
            concerns.append(Concern(
                field="amount_gross",
                severity="warning",
                reason=f"Rekenkundige inconsistentie: net({net}) + vat({vat}) = {float(net)+float(vat):.2f} ≠ gross({gross}), verschil: {diff:.2f}",
                suggested_next_steps=["Controleer de bedragen op de originele factuur", "Corrigeer het afwijkende bedrag via [c]"],
                source="validator",
            ))

    # Invoice date not in the future
    invoice_date_str = val("invoice_date")
    if invoice_date_str:
        try:
            invoice_date = date.fromisoformat(str(invoice_date_str))
            if invoice_date > date.today():
                concerns.append(Concern(
                    field="invoice_date",
                    severity="warning",
                    reason=f"Factuurdatum {invoice_date_str} ligt in de toekomst",
                    suggested_next_steps=["Controleer of de datum correct is", "Corrigeer indien nodig via [c]"],
                    source="validator",
                ))
        except ValueError:
            concerns.append(Concern(
                field="invoice_date",
                severity="blocking",
                reason=f"Ongeldige datumnotatie: {invoice_date_str} (verwacht YYYY-MM-DD)",
                suggested_next_steps=["Corrigeer de datum via [c] naar het formaat YYYY-MM-DD"],
                source="validator",
            ))

    has_blocking = any(c.severity == "blocking" for c in concerns)
    return ValidationResult(ok=not has_blocking, concerns=concerns)
