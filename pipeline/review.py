import time

from core import tenant as tenant_io
from core.models import Concern, ExtractionResult, InvoiceRecord, ProposedBooking, ReviewOutcome

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

_SEVERITY_ICON = {"blocking": "✗", "warning": "!", "info": "i"}
_SEVERITY_ORDER = {"blocking": 0, "warning": 1, "info": 2}


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


def _print_extraction(record: InvoiceRecord) -> None:
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


def _print_concerns(concerns: list[Concern]) -> None:
    if not concerns:
        return
    sorted_concerns = sorted(concerns, key=lambda c: _SEVERITY_ORDER.get(c.severity, 9))
    print("\nAGENT- EN VALIDATOR-BEVINDINGEN")
    for c in sorted_concerns:
        icon = _SEVERITY_ICON.get(c.severity, "?")
        label = f"[{c.field}]" if c.field else "[algemeen]"
        source_tag = f"({c.source})"
        print(f"  {icon} {c.severity.upper():<8} {label} {c.reason}  {source_tag}")
        for step in c.suggested_next_steps:
            print(f"      → {step}")


def _print_booking(proposed: ProposedBooking) -> None:
    # Invoice metadata
    print("\nFACTUURGEGEVENS")
    print(f"  Leverancier     : {proposed.vendor}")
    print(f"  Factuurnummer   : {proposed.invoice_number or '—'}")
    print(f"  Factuurdatum    : {proposed.invoice_date or '—'}")
    print(f"  Valuta          : {proposed.currency}")
    if proposed.kostenplaats:
        print(f"  Kostenplaats    : {proposed.kostenplaats}")

    # Invoice line items
    if proposed.line_items:
        print("\nFACTUUUREGELS")
        print(f"  {'Omschrijving':<32} {'Aantal':>6}  {'Stukprijs':>10}  {'Bedrag':>10}  {'BTW':>5}  Rekening")
        print("  " + "-" * 78)
        for li in proposed.line_items:
            qty = f"{li.quantity:.2f}" if li.quantity is not None else "—"
            price = f"€ {li.unit_price:>8.2f}" if li.unit_price is not None else "—"
            vat = f"{int(li.vat_rate * 100)}%" if li.vat_rate is not None else "—"
            # Find matching journal line account for this item
            expense_line = next((l for l in proposed.journal_lines if l.side == "D" and "BTW" not in l.description), None)
            account = expense_line.account if expense_line else "—"
            print(f"  {li.description[:32]:<32} {qty:>6}  {price:>10}  € {li.amount:>8.2f}  {vat:>5}  {account}")

    # Journal entry
    print("\nJOURNAALPOST")
    print(f"  {'D/C':<3}  {'Rekening':<8}  {'Omschrijving':<28}  {'Bedrag':>10}")
    print("  " + "-" * 56)
    for line in proposed.journal_lines:
        print(f"  {line.side:<3}  {line.account:<8}  {line.description:<28}  € {line.amount:>8.2f}")
    print(f"  {'':3}  {'':8}  {'Totaal incl. BTW':<28}  € {proposed.amount_gross:>8.2f}")


def _print_menu(has_blocking: bool) -> None:
    print()
    print("-" * 56)
    if has_blocking:
        print("  [a] Goedkeuren  (GEBLOKKEERD — zie blocking concerns)")
        print("  [fa] Force-approve (overschrijf blocking concerns)")
    else:
        print("  [a] Goedkeuren & boeken")
    print("  [c] Veld corrigeren")
    print("  [e] Escaleren")
    print("  [q] Afsluiten (opslaan als geëscaleerd)")
    print("  [x] Annuleren (niets opslaan, niets boeken)")
    print("-" * 56)


def _correct_field(record: InvoiceRecord, corrections: dict) -> list[str]:
    """Interactive field correction. Returns list of saved rule texts."""
    from core.rule_formulator import formulate_rule, check_rule_conflicts
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

            # LLM formulates the rule
            print("  LLM formuleert concept-regel...")
            original_extraction = {k: {"value": v.value, "confidence": v.confidence} for k, v in ex.fields.items()}
            proposal = formulate_rule(
                raw_text=record.raw_text,
                original_extraction=original_extraction,
                field_name=canonical,
                old_value=current_val,
                new_value=new_val,
                operator_note=note,
                vendor_name=vendor_name,
            )

            print(f"\n  Conceptregel:")
            print(f"    \"{proposal.rule_text}\"")
            print(f"    Scope: {proposal.scope}" + (f" — {proposal.scope_value}" if proposal.scope_value else ""))
            if proposal.generalization_warning:
                print(f"  ⚠ Generalisatie-waarschuwing: {proposal.generalization_warning}")

            edit = input("\n  Aanpassen? (Enter om te bevestigen, of typ nieuwe tekst) > ").strip()
            final_rule_text = edit if edit else proposal.rule_text

            # Conflict check
            from core.tenant import load_learned_rules
            existing_rules = load_learned_rules(record.tenant_slug)
            print("  Conflictcheck bezig...")
            conflict = check_rule_conflicts(final_rule_text, existing_rules)

            if conflict.has_conflict:
                print(f"\n  ⚠ MOGELIJK CONFLICT GEDETECTEERD:")
                for cr in conflict.conflicting_rules:
                    print(f"    Conflicteert met: \"{cr}\"")
                print(f"  Uitleg: {conflict.explanation}")
                print()
                print("    [1] Toch opslaan")
                print("    [2] Regel herformuleren")
                print("    [3] Annuleren")
                conflict_choice = input("  > ").strip()
                if conflict_choice == "3":
                    print("  Opslaan geannuleerd.")
                    conflict_decision = "cancel"
                elif conflict_choice == "2":
                    final_rule_text = input("  Nieuwe formulering: > ").strip()
                    conflict_decision = "reformulate"
                else:
                    conflict_decision = "save_anyway"
                corrections[f"_conflict_check_{canonical}"] = {
                    "has_conflict": True,
                    "conflicting_rules": conflict.conflicting_rules,
                    "explanation": conflict.explanation,
                    "operator_decision": conflict_decision,
                }
                if conflict_decision == "cancel":
                    more = input("\n  Nog een veld corrigeren? [j/n] > ").strip().lower()
                    if more != "j":
                        break
                    continue
            else:
                corrections[f"_conflict_check_{canonical}"] = {"has_conflict": False}

            # Save rule and example
            from core.tenant import append_rule, append_example
            from core.models import RuleProposal
            import copy
            final_proposal = copy.copy(proposal)
            final_proposal.rule_text = final_rule_text

            append_rule(record.tenant_slug, final_proposal, record.run_id)

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
            append_example(record.tenant_slug, example_entry)
            print(f"  Bevestigd. Regel opgeslagen → tenants/{record.tenant_slug}/learned_rules.md (run: {record.run_id})")
            print(f"  Voorbeeld opgeslagen → tenants/{record.tenant_slug}/examples.jsonl")
            rules_saved.append(final_rule_text)

        more = input("\n  Nog een veld corrigeren? [j/n] > ").strip().lower()
        if more != "j":
            break

    return rules_saved


def run_review(record: InvoiceRecord, proposed: ProposedBooking, tenant_config=None, validation=None) -> ReviewOutcome:
    from pipeline.propose import propose as repropose
    start = time.time()
    corrections: dict = {}
    rules_saved: list[str] = []

    has_blocking = any(c.severity == "blocking" for c in proposed.concerns)

    _print_header(record, proposed)
    _print_extraction(record)
    _print_concerns(proposed.concerns)
    _print_booking(proposed)

    while True:
        _print_menu(has_blocking)
        choice = input("> ").strip().lower()

        if choice == "a":
            if has_blocking:
                print("  Geblokkeerd door blocking concerns. Gebruik [fa] om toch goed te keuren.")
                continue
            duration = time.time() - start
            print("\n  Goedgekeurd.")
            return ReviewOutcome(
                action="approve",
                corrections=corrections,
                rules_saved=rules_saved,
                duration_seconds=round(duration, 1),
            )
        elif choice == "fa":
            print()
            print("  ⚠ Je staat op het punt te boeken ondanks blocking concerns.")
            confirmation = input("  Typ 'JA IK NEEM VERANTWOORDELIJKHEID' om te bevestigen: ").strip()
            if confirmation != "JA IK NEEM VERANTWOORDELIJKHEID":
                print("  Bevestiging niet correct. Force-approve geannuleerd.")
                continue
            duration = time.time() - start
            print("\n  Force-approve bevestigd. Boekstuk aangemaakt.")
            return ReviewOutcome(
                action="force_approve",
                corrections=corrections,
                rules_saved=rules_saved,
                force_approve=True,
                operator_confirmation=confirmation,
                duration_seconds=round(duration, 1),
            )
        elif choice == "c":
            new_rules = _correct_field(record, corrections)
            rules_saved.extend(new_rules)
            # Re-propose with corrected extraction so journal lines reflect corrections
            if tenant_config and validation and record.extraction:
                updated = repropose(record.extraction, validation, tenant_config)
                proposed.journal_lines = updated.journal_lines
                proposed.vendor = updated.vendor
                proposed.invoice_number = updated.invoice_number
                proposed.invoice_date = updated.invoice_date
                proposed.amount_gross = updated.amount_gross
                proposed.currency = updated.currency
                proposed.line_items = updated.line_items
                proposed.kostenplaats = updated.kostenplaats
                record.proposed_booking = proposed
            has_blocking = any(c.severity == "blocking" for c in proposed.concerns)
            _print_booking(proposed)
        elif choice == "e":
            reason = input("  Reden voor escalatie: ").strip()
            record.escalation_reason = reason
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
        elif choice == "x":
            print("\n  Geannuleerd. Geen actie ondernomen, niets opgeslagen.")
            duration = time.time() - start
            return ReviewOutcome(
                action="cancel",
                corrections={},
                rules_saved=[],
                duration_seconds=round(duration, 1),
            )
        else:
            print("  Ongeldige keuze. Kies a, fa, c, e, q of x.")
