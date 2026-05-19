"""
Invoice processing pipeline entry point.

Usage:
    python main.py <invoice_file> --tenant <slug>
    python main.py samples/invoice_001.txt --tenant acme
    python main.py samples/invoice_001.txt --auto-classify   # niet aanbevolen
"""
import argparse
import sys

from adapters.bookkeeping import MockBookkeepingAdapter
from adapters.mailbox import MockMailboxAdapter
from core import tenant as tenant_io
from pipeline.book_or_escalate import book, escalate
from pipeline.classify_tenant import auto_classify_tenant, classify_tenant
from pipeline.extract import extract
from pipeline.ingest import ingest
from pipeline.log import init_run_log, log_step, save_run_log
from pipeline.propose import propose
from pipeline.review import run_review
from pipeline.validate import validate


def run_pipeline(invoice_file: str, tenant_slug: str | None = None, auto_classify: bool = False, source_type: str | None = None, env: str | None = None) -> None:
    target_env = env or config.BOOKKEEPING_ENV
    bookkeeping = MockBookkeepingAdapter(target_env=target_env)
    mailbox = MockMailboxAdapter()
    print(f"Omgeving: {target_env.upper()} ({config.bookkeeping_api_url(target_env)})")

    # 1. Ingest
    record = ingest(invoice_file, source_type=source_type)
    run_log = init_run_log(record)
    log_step(run_log, "ingest", {
        "status": "ok",
        "raw_text_chars": len(record.raw_text),
        "source_type": record.source_type,
    })

    # 2. Classify tenant
    if tenant_slug:
        record = classify_tenant(record, tenant_slug)
        classify_method = "cli_argument"
    elif auto_classify:
        record = auto_classify_tenant(record)
        classify_method = "llm_auto"
    else:
        available = tenant_io.list_tenants()
        slugs_str = ", ".join(sorted(available)) if available else "(geen tenants)"
        print("Fout: --tenant is verplicht.")
        print(f"Beschikbare tenants: {slugs_str}")
        print("Gebruik --auto-classify voor automatische detectie (niet aanbevolen voor productie).")
        sys.exit(1)

    log_step(run_log, "classify_tenant", {
        "status": "ok",
        "tenant_slug": record.tenant_slug,
        "method": classify_method,
        "auto_classify_warning": auto_classify,
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
        "line_items": [
            {
                "description": li.description,
                "quantity": li.quantity,
                "unit_price": li.unit_price,
                "amount": li.amount,
                "vat_rate": li.vat_rate,
            }
            for li in extraction.line_items
        ],
        "agent_concerns": [
            {
                "field": c.field,
                "severity": c.severity,
                "reason": c.reason,
                "suggested_next_steps": c.suggested_next_steps,
            }
            for c in extraction.agent_concerns
        ],
    })

    # 5. Validate
    validation = validate(record, extraction, tenant_config)
    record.validation = validation
    record.status = "validated"
    log_step(run_log, "validate", {
        "status": "ok",
        "ok": validation.ok,
        "concerns": [
            {"field": c.field, "reason": c.reason, "severity": c.severity, "source": c.source}
            for c in validation.concerns
        ],
    })

    # 6. Propose
    proposed = propose(extraction, validation, tenant_config)
    record.proposed_booking = proposed
    record.status = "proposed"
    log_step(run_log, "propose", {
        "status": "ok",
        "journal_lines": [
            {"side": l.side, "account": l.account, "amount": l.amount, "description": l.description}
            for l in proposed.journal_lines
        ],
        "total_concerns": len(proposed.concerns),
        "blocking_concerns": sum(1 for c in proposed.concerns if c.severity == "blocking"),
    })

    # 7. Review (operator CLI)
    outcome = run_review(record, proposed)
    record.review_outcome = outcome
    log_step(run_log, "review", {
        "status": outcome.action,
        "operator_action": outcome.action,
        "corrections": outcome.corrections,
        "rules_saved": outcome.rules_saved,
        "force_approve": outcome.force_approve,
        "operator_confirmation": outcome.operator_confirmation,
        "duration_seconds": outcome.duration_seconds,
    })

    # 8. Book or escalate
    if outcome.action in ("approve", "force_approve"):
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
    parser.add_argument("invoice_file", help="Pad naar factuur")
    parser.add_argument("--tenant", "-t", default=None, help="Tenant slug (bijv. acme)")
    parser.add_argument("--auto-classify", action="store_true", help="Automatische tenant-detectie via LLM (niet aanbevolen)")
    parser.add_argument("--source-type", default=None, choices=["plain_text", "pdf", "html", "excel", "scan"],
                        help="Bestandstype overschrijven (default: afgeleid van extensie)")
    args = parser.parse_args()
    run_pipeline(args.invoice_file, args.tenant, args.auto_classify, args.source_type)


if __name__ == "__main__":
    main()
