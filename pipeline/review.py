import time
from datetime import datetime, timezone

from core import tenant as tenant_io
from core.models import ExtractionResult, InvoiceRecord, ProposedBooking, ReviewOutcome, RunLog, ValidationResult

_FIELD_ALIASES = {
    "vendor": "vendor",
    "invoice_number": "invoice_number",
    "invoice_date": "invoice_date",
    "due_date": "due_date",
    "amount_gross": "amount_gross",
    "amount_vat": "amount_vat",
    "amount_net": "amount_net",
    "vat_rate": "vat_rate",
    "currency": "currency",
    "description": "description",
    "suggested_acct": "suggested_account_code",
    "suggested_account_code": "suggested_account_code",
}


def _conf_str(extraction: ExtractionResult, field_name: str) -> str:
    fv = extraction.fields.get(field_name)
    if fv is None:
        return "  —  "
    marker = " ⚠" if fv.confidence < 0.80 else ""
    return f"[{fv.confidence:.2f}]{marker}"


def _val_str(extraction: ExtractionResult, field_name: str) -> str:
    fv = extraction.fields.get(field_name)
    if fv is None or fv.value is None:
        return "—"
    return str(fv.value)


def _print_header(record: InvoiceRecord, proposed: ProposedBooking) -> None:
    print()
    print("=" * 56)
    print(f"  FACTUURVERWERKING  |  Run: {record.run_id}")
    print(f"  Klant: {proposed.vendor[:20]:<20} |  Bestand: {record.source_file}")
    print("=" * 56)


def _print_extraction(record: InvoiceRecord, validation: ValidationResult | None) -> None:
    ex = record.extraction
    if ex is None:
        return
    print("\nEXTRACTIE RESULTAAT")
    fields_order = [
        "vendor", "invoice_number", "invoice_date", "due_date",
        "amount_gross", "amount_vat", "amount_net", "vat_rate",
        "currency", "description", "suggested_account_code",
    ]
    for f in fields_order:
        label = f if f != "suggested_account_code" else "suggested_acct"
        val = _val_str(ex, f)
        cs = _conf_str(ex, f)
        print(f"  {label:<22} {val:<26} {cs}")

    print(f"\n  overall_confidence: {ex.overall_confidence:.2f}")
    if ex.uncertainty_notes:
        print(f"  Opmerkingen LLM: \"{ex.uncertainty_notes}\"")

    if validation and validation.issues:
        print("\n  VALIDATIE WAARSCHUWINGEN:")
        for issue in validation.issues:
            icon = "✗" if issue.severity == "error" else "!"
            print(f"    {icon} [{issue.field}] {issue.reason}")


def _print_booking(proposed: ProposedBooking) -> None:
    print("\nVOORGESTELD BOEKSTUK")
    for line in proposed.journal_lines:
        print(f"  {line.side}  {line.account}  {line.description:<28} € {line.amount:>8.2f}")


def _print_menu() -> None:
    print()
    print("-" * 56)
    print("  [a] Goedkeuren & boeken")
    print("  [c] Veld corrigeren")
    print("  [e] Escaleren")
    print("  [q] Afsluiten (opslaan als geëscaleerd)")
    print("-" * 56)


def _correct_field(record: InvoiceRecord, corrections: dict) -> list[str]:
    """Interactive field correction. Returns list of saved rule texts."""
    ex = record.extraction
    rules_saved = []
    while True:
        field_input = input("Welk veld corrigeren? (bijv. suggested_acct, vendor, amount_gross) > ").strip()
        canonical = _FIELD_ALIASES.get(field_input)
        if not canonical:
            print(f"  Onbekend veld '{field_input}'. Beschikbare velden: {', '.join(_FIELD_ALIASES.keys())}")
            continue

        current = ex.fields.get(canonical)
        current_val = current.value if current else None
        print(f"  Huidige waarde : {current_val}")

        new_val = input("  Nieuwe waarde  : ").strip()
        note = input("  Optionele notitie (Enter om over te slaan): ").strip()

        # Apply correction to extraction in-place
        if ex.fields.get(canonical):
            ex.fields[canonical].value = new_val
        corrections[canonical] = new_val
        print("  Veld bijgewerkt.")

        save = input("\n  Wil je deze correctie opslaan als leerregel? [j/n] > ").strip().lower()
        if save == "j" and record.tenant_slug:
            vendor_fv = ex.fields.get("vendor")
            vendor_name = vendor_fv.value if vendor_fv else "onbekend"
            note_part = f" Reden: {note}" if note else ""
            rule_text = (
                f'Facturen van "{vendor_name}": {canonical} = {new_val}.{note_part}'
            )
            tenant_io.append_rule(record.tenant_slug, rule_text)

            # Build example entry
            input_snippet = {
                "vendor": vendor_name,
                "raw_snippet": record.raw_text[:200],
            }
            output_fields = {k: v.value for k, v in ex.fields.items() if v.value is not None}
            from datetime import datetime, timezone
            example_entry = {
                "id": f"ex-{record.run_id}",
                "added_at": datetime.now(timezone.utc).isoformat(),
                "operator_note": note or f"{canonical} gecorrigeerd naar {new_val}",
                "input": input_snippet,
                "output": output_fields,
            }
            tenant_io.append_example(record.tenant_slug, example_entry)
            print(f"  Regel opgeslagen → tenants/{record.tenant_slug}/learned_rules.md")
            print(f"  Voorbeeld opgeslagen → tenants/{record.tenant_slug}/examples.jsonl")
            rules_saved.append(rule_text)

        more = input("\n  Nog een veld corrigeren? [j/n] > ").strip().lower()
        if more != "j":
            break

    return rules_saved


def run_review(
    record: InvoiceRecord,
    proposed: ProposedBooking,
    validation: ValidationResult | None = None,
) -> ReviewOutcome:
    start = time.time()
    corrections: dict = {}
    rules_saved: list[str] = []

    _print_header(record, proposed)
    _print_extraction(record, validation)
    _print_booking(proposed)

    while True:
        _print_menu()
        choice = input("> ").strip().lower()

        if choice == "a":
            duration = time.time() - start
            print(f"\n  Goedgekeurd.")
            return ReviewOutcome(
                action="approve",
                corrections=corrections,
                rules_saved=rules_saved,
                duration_seconds=round(duration, 1),
            )
        elif choice == "c":
            new_rules = _correct_field(record, corrections)
            rules_saved.extend(new_rules)
            # Reprint booking after correction
            _print_booking(proposed)
        elif choice == "e":
            reason = input("  Reden voor escalatie: ").strip()
            duration = time.time() - start
            return ReviewOutcome(
                action="escalate",
                corrections=corrections,
                rules_saved=rules_saved,
                duration_seconds=round(duration, 1),
            )
        elif choice == "q":
            duration = time.time() - start
            return ReviewOutcome(
                action="quit",
                corrections=corrections,
                rules_saved=rules_saved,
                duration_seconds=round(duration, 1),
            )
        else:
            print("  Ongeldige keuze. Kies a, c, e of q.")
