"""
Invoice processing pipeline entry point.

Usage:
    python main.py <invoice_file> --tenant <slug>
    python main.py samples/invoice_001.txt --tenant acme
"""
import argparse
import sys

from adapters.bookkeeping import MockBookkeepingAdapter
from adapters.mailbox import MockMailboxAdapter
from core import tenant as tenant_io
from pipeline.book_or_escalate import book, escalate
from pipeline.classify_tenant import classify_tenant
from pipeline.extract import extract
from pipeline.ingest import ingest
from pipeline.log import init_run_log, log_step, save_run_log
from pipeline.propose import propose
from pipeline.review import run_review
from pipeline.validate import validate


def run_pipeline(invoice_file: str, tenant_slug: str | None = None) -> None:
    bookkeeping = MockBookkeepingAdapter()
    mailbox = MockMailboxAdapter()

    # 1. Ingest
    record = ingest(invoice_file)
    run_log = init_run_log(record)
    log_step(run_log, "ingest", {"status": "ok", "raw_text_chars": len(record.raw_text)})

    # 2. Classify tenant
    record = classify_tenant(record, tenant_slug)
    if not record.tenant_slug:
        print("Fout: kon geen tenant bepalen. Geef --tenant mee.")
        sys.exit(1)
    log_step(run_log, "classify_tenant", {
        "status": "ok",
        "tenant_slug": record.tenant_slug,
        "method": "cli_argument" if tenant_slug else "llm",
    })
    run_log.tenant_slug = record.tenant_slug

    # 3. Load tenant config
    tenant_config = tenant_io.load_tenant_config(record.tenant_slug)

    # 4. Extract
    print(f"\nFactuur wordt verwerkt voor klant: {tenant_config.name}")
    print("LLM-extractie bezig...")
    extraction = extract(record, tenant_config)
    record.extraction = extraction
    record.status = "extracted"
    log_step(run_log, "extract", {
        "status": "ok",
        "system_prompt": extraction.system_prompt,
        "user_prompt": extraction.user_prompt,
        "llm_response_raw": extraction.llm_response_raw,
        "parsed_fields": {
            k: {"value": v.value, "confidence": v.confidence}
            for k, v in extraction.fields.items()
        },
        "overall_confidence": extraction.overall_confidence,
        "uncertainty_notes": extraction.uncertainty_notes,
    })

    # 5. Validate
    validation = validate(record, extraction, tenant_config)
    record.validation = validation
    record.status = "validated"
    log_step(run_log, "validate", {
        "status": "ok",
        "ok": validation.ok,
        "issues": [
            {"field": i.field, "reason": i.reason, "severity": i.severity}
            for i in validation.issues
        ],
    })

    # 6. Propose
    proposed = propose(extraction, tenant_config)
    record.proposed_booking = proposed
    record.status = "proposed"
    log_step(run_log, "propose", {
        "status": "ok",
        "journal_lines": [
            {"side": l.side, "account": l.account, "amount": l.amount, "description": l.description}
            for l in proposed.journal_lines
        ],
    })

    # 7. Review (operator CLI)
    outcome = run_review(record, proposed, validation)
    record.review_outcome = outcome
    log_step(run_log, "review", {
        "status": outcome.action,
        "operator_action": outcome.action,
        "corrections": outcome.corrections,
        "rules_saved": outcome.rules_saved,
        "duration_seconds": outcome.duration_seconds,
    })

    # 8. Book or escalate
    if outcome.action == "approve":
        booking_id = book(proposed, bookkeeping)
        record.status = "booked"
        log_step(run_log, "book_or_escalate", {"status": "booked", "booking_id": booking_id})
        print(f"\n  Booking: {booking_id}")
    elif outcome.action == "escalate":
        reason = record.escalation_reason or "Geëscaleerd door operator"
        escalate(record, reason, mailbox)
        record.status = "escalated"
        log_step(run_log, "book_or_escalate", {"status": "escalated", "reason": reason})
    else:
        record.status = "escalated"
        log_step(run_log, "book_or_escalate", {"status": "quit"})

    # 9. Save run log
    run_log.final_status = record.status
    log_path = save_run_log(run_log)
    print(f"  Run log: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Swoep.AI invoice processor")
    parser.add_argument("invoice_file", help="Pad naar factuur (plain text)")
    parser.add_argument("--tenant", "-t", default=None, help="Tenant slug (bijv. acme)")
    args = parser.parse_args()
    run_pipeline(args.invoice_file, args.tenant)


if __name__ == "__main__":
    main()
