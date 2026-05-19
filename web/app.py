"""
Swoep.AI web frontend.

Start with:
    python web/app.py
Then open http://localhost:5000
"""
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from flask import Flask, redirect, render_template, request, url_for

import config
from adapters.bookkeeping import MockBookkeepingAdapter
from adapters.mailbox import MockMailboxAdapter
from core import tenant as tenant_io
from pipeline.book_or_escalate import book, escalate
from pipeline.classify_tenant import classify_tenant
from pipeline.extract import extract
from pipeline.ingest import ingest
from pipeline.log import init_run_log, log_step, save_run_log
from pipeline.propose import propose
from pipeline.validate import validate

app = Flask(__name__)

# In-memory state: run_id → dict with record, proposed, validation, tenant_config
_sessions: dict = {}


def _peek_sender(filepath: Path) -> str:
    """Read the first non-empty line of an invoice file as the sender name."""
    try:
        for line in filepath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.lower().startswith("factuur") and not line.lower().startswith("invoice") and not line.lower().startswith("rechnung"):
                return line
    except Exception:
        pass
    return filepath.stem


def _inbox_emails() -> list[dict]:
    """Build a list of mock email metadata from the samples directory."""
    emails = []
    for path in sorted(config.SAMPLES_DIR.iterdir()):
        if path.suffix.lower() not in (".txt", ".pdf", ".html", ".xlsx"):
            continue
        sender = _peek_sender(path)
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%d-%m-%Y %H:%M")
        # Guess tenant from filename
        default_tenant = "betaworks" if "betaworks" in path.name else "acme"
        emails.append({
            "filename": path.name,
            "sender": sender,
            "subject": f"Factuur – {path.stem.replace('_', ' ').title()}",
            "date": modified,
            "default_tenant": default_tenant,
        })
    return emails


@app.route("/")
def inbox():
    emails = _inbox_emails()
    tenants = sorted(tenant_io.list_tenants())
    return render_template("inbox.html", emails=emails, tenants=tenants)


@app.route("/process", methods=["POST"])
def process():
    filename = request.form.get("filename", "")
    tenant_slug = request.form.get("tenant", "")

    filepath = config.SAMPLES_DIR / filename
    if not filepath.exists():
        return f"Bestand niet gevonden: {filename}", 404

    # Run pipeline steps 1–5
    record = ingest(str(filepath))
    run_log = init_run_log(record)
    log_step(run_log, "ingest", {"status": "ok", "source_type": record.source_type})

    record = classify_tenant(record, tenant_slug)
    log_step(run_log, "classify_tenant", {"status": "ok", "tenant_slug": tenant_slug})

    tenant_config = tenant_io.load_tenant_config(tenant_slug)

    extraction = extract(record, tenant_config)
    record.extraction = extraction
    record.status = "extracted"
    log_step(run_log, "extract", {
        "status": "ok",
        "parsed_fields": {k: {"value": v.value, "confidence": v.confidence} for k, v in extraction.fields.items()},
        "overall_confidence": extraction.overall_confidence,
        "agent_concerns": [{"field": c.field, "severity": c.severity, "reason": c.reason} for c in extraction.agent_concerns],
    })

    validation = validate(record, extraction, tenant_config)
    record.validation = validation
    record.status = "validated"
    log_step(run_log, "validate", {"status": "ok", "ok": validation.ok})

    proposed = propose(extraction, validation, tenant_config)
    record.proposed_booking = proposed
    record.status = "proposed"
    log_step(run_log, "propose", {"status": "ok"})

    _sessions[record.run_id] = {
        "record": record,
        "proposed": proposed,
        "validation": validation,
        "tenant_config": tenant_config,
        "run_log": run_log,
    }

    return redirect(url_for("review", run_id=record.run_id))


@app.route("/review/<run_id>")
def review(run_id: str):
    session = _sessions.get(run_id)
    if not session:
        return redirect(url_for("inbox"))

    record = session["record"]
    proposed = session["proposed"]
    tenant_config = session["tenant_config"]
    extraction = record.extraction

    has_blocking = any(c.severity == "blocking" for c in proposed.concerns)

    fields = []
    display_fields = [
        ("vendor", "Leverancier"),
        ("invoice_number", "Factuurnummer"),
        ("invoice_date", "Factuurdatum"),
        ("due_date", "Vervaldatum"),
        ("amount_net", "Subtotaal"),
        ("amount_vat", "BTW-bedrag"),
        ("amount_gross", "Totaal"),
        ("vat_rate", "BTW-percentage"),
        ("currency", "Valuta"),
        ("description", "Omschrijving"),
        ("suggested_account_code", "Rekening"),
        ("kostenplaats", "Kostenplaats"),
    ]
    for field_key, label in display_fields:
        fv = extraction.fields.get(field_key) if extraction else None
        value = str(fv.value) if fv and fv.value is not None else "—"
        confidence = fv.confidence if fv else None
        low = confidence is not None and confidence < tenant_config.confidence_threshold
        fields.append({
            "key": field_key,
            "label": label,
            "value": value,
            "confidence": f"{confidence:.2f}" if confidence is not None else None,
            "low": low,
        })

    concerns = sorted(proposed.concerns, key=lambda c: {"blocking": 0, "warning": 1, "info": 2}.get(c.severity, 9))

    return render_template(
        "review.html",
        run_id=run_id,
        record=record,
        proposed=proposed,
        fields=fields,
        concerns=concerns,
        has_blocking=has_blocking,
        overall_confidence=f"{extraction.overall_confidence:.2f}" if extraction else "—",
        tenant_config=tenant_config,
    )


@app.route("/correct/<run_id>", methods=["POST"])
def correct(run_id: str):
    from core.models import FieldValue
    from pipeline.propose import propose as repropose

    session = _sessions.get(run_id)
    if not session:
        return redirect(url_for("inbox"))

    field_key = request.form.get("field", "").strip()
    new_value = request.form.get("value", "").strip()

    record = session["record"]
    extraction = record.extraction
    tenant_config = session["tenant_config"]
    validation = session["validation"]

    if extraction and field_key and new_value:
        if field_key in extraction.fields:
            extraction.fields[field_key].value = new_value
        else:
            extraction.fields[field_key] = FieldValue(value=new_value, confidence=1.0)

        updated = repropose(extraction, validation, tenant_config)
        session["proposed"] = updated
        record.proposed_booking = updated

    return redirect(url_for("review", run_id=run_id))


@app.route("/approve/<run_id>", methods=["POST"])
def approve(run_id: str):
    session = _sessions.get(run_id)
    if not session:
        return redirect(url_for("inbox"))

    record = session["record"]
    proposed = session["proposed"]
    run_log = session["run_log"]

    bookkeeping = MockBookkeepingAdapter()
    booking_id, booking_audit = book(proposed, bookkeeping)
    record.status = "booked"

    log_step(run_log, "review", {"status": "approve", "operator_action": "approve"})
    log_step(run_log, "book_or_escalate", {"status": "booked", "booking_id": booking_id, **booking_audit})
    run_log.final_status = "booked"
    log_path = save_run_log(run_log)

    del _sessions[run_id]

    return render_template("done.html",
        action="geboekt",
        run_id=run_id,
        booking_id=booking_id,
        log_path=str(log_path),
        tenant=record.tenant_slug,
        vendor=proposed.vendor,
    )


@app.route("/escalate/<run_id>", methods=["POST"])
def escalate_route(run_id: str):
    session = _sessions.get(run_id)
    if not session:
        return redirect(url_for("inbox"))

    record = session["record"]
    run_log = session["run_log"]
    reason = request.form.get("reason", "Geëscaleerd via webinterface").strip()

    mailbox = MockMailboxAdapter()
    record.escalation_reason = reason
    escalate(record, reason, mailbox)
    record.status = "escalated"

    log_step(run_log, "review", {"status": "escalate", "operator_action": "escalate"})
    log_step(run_log, "book_or_escalate", {"status": "escalated", "reason": reason})
    run_log.final_status = "escalated"
    save_run_log(run_log)

    del _sessions[run_id]

    return render_template("done.html",
        action="geëscaleerd",
        run_id=run_id,
        booking_id=None,
        log_path=None,
        tenant=record.tenant_slug,
        vendor=record.proposed_booking.vendor if record.proposed_booking else "—",
    )


@app.route("/cancel/<run_id>")
def cancel(run_id: str):
    _sessions.pop(run_id, None)
    return redirect(url_for("inbox"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
