from __future__ import annotations
import asyncio
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import tenant as tenant_io
from pipeline.ingest import ingest
from pipeline.classify_tenant import classify_tenant
from pipeline.extract import extract
from pipeline.validate import validate
from pipeline.propose import propose
from pipeline.log import init_run_log, log_step
from web.mailbox_data import get_email
from web import state as store
from web.state import PipelinePhase

router = APIRouter()


class ProcessRequest(BaseModel):
    email_id: str
    tenant_slug: str


@router.post("/process", status_code=202)
async def process_invoice(req: ProcessRequest):
    email = get_email(req.email_id)
    if not email:
        raise HTTPException(status_code=404, detail="E-mail niet gevonden")

    tenants = tenant_io.list_tenants()
    if req.tenant_slug not in tenants:
        raise HTTPException(status_code=400, detail=f"Onbekende tenant: {req.tenant_slug}")

    record = ingest(email.attachment_path)
    record = classify_tenant(record, req.tenant_slug)
    run_log = init_run_log(record)
    log_step(run_log, "ingest", {
        "status": "ok",
        "raw_text_chars": len(record.raw_text),
        "source_type": record.source_type,
    })
    log_step(run_log, "classify_tenant", {
        "status": "ok",
        "tenant_slug": record.tenant_slug,
        "method": "web_ui",
    })

    s = store.create(record.run_id)
    s.record = record
    s.phase = PipelinePhase.PENDING
    # store run_log on the state for later saving
    s._run_log = run_log  # type: ignore[attr-defined]

    asyncio.create_task(_run_pipeline_bg(record.run_id))
    return {"run_id": record.run_id, "status": "running"}


async def _run_pipeline_bg(run_id: str) -> None:
    store.update(run_id, phase=PipelinePhase.RUNNING)
    s = store.get(run_id)
    if s is None:
        return
    record = s.record
    run_log = s._run_log  # type: ignore[attr-defined]
    try:
        tenant_config = await asyncio.to_thread(tenant_io.load_tenant_config, record.tenant_slug)
        extraction = await asyncio.to_thread(extract, record, tenant_config)
        record.extraction = extraction
        record.status = "extracted"
        log_step(run_log, "extract", {
            "status": "ok",
            "parsed_fields": {
                k: {"value": v.value, "confidence": v.confidence}
                for k, v in extraction.fields.items()
            },
            "overall_confidence": extraction.overall_confidence,
            "line_items": [asdict(li) for li in extraction.line_items],
            "agent_concerns": [asdict(c) for c in extraction.agent_concerns],
        })

        validation = await asyncio.to_thread(validate, record, extraction, tenant_config)
        record.validation = validation
        record.status = "validated"
        log_step(run_log, "validate", {
            "status": "ok",
            "ok": validation.ok,
            "concerns": [asdict(c) for c in validation.concerns],
        })

        proposed = await asyncio.to_thread(propose, extraction, validation, tenant_config)
        record.proposed_booking = proposed
        record.status = "proposed"
        log_step(run_log, "propose", {
            "status": "ok",
            "journal_lines": [asdict(l) for l in proposed.journal_lines],
            "total_concerns": len(proposed.concerns),
            "blocking_concerns": sum(1 for c in proposed.concerns if c.severity == "blocking"),
        })

        store.update(run_id, phase=PipelinePhase.PROPOSED, record=record)
    except Exception as exc:
        store.update(run_id, phase=PipelinePhase.ERROR, error=str(exc))


def _serialise_run(run_id: str) -> dict:
    s = store.get(run_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Run niet gevonden")

    base = {"run_id": run_id, "phase": s.phase}

    if s.phase == PipelinePhase.ERROR:
        return {**base, "error": s.error}

    if s.phase != PipelinePhase.PROPOSED:
        return base

    record = s.record
    ex = record.extraction
    proposed = record.proposed_booking

    fields = {
        k: {"value": v.value, "confidence": v.confidence}
        for k, v in ex.fields.items()
    }
    concerns = [
        {
            "field": c.field,
            "severity": c.severity,
            "reason": c.reason,
            "suggested_next_steps": c.suggested_next_steps,
            "source": c.source,
        }
        for c in proposed.concerns
    ]
    journal_lines = [
        {"side": l.side, "account": l.account, "amount": l.amount, "description": l.description}
        for l in proposed.journal_lines
    ]
    line_items = [
        {
            "description": li.description,
            "quantity": li.quantity,
            "unit_price": li.unit_price,
            "amount": li.amount,
            "vat_rate": li.vat_rate,
        }
        for li in proposed.line_items
    ]

    return {
        **base,
        "tenant_slug": record.tenant_slug,
        "source_file": record.source_file,
        "overall_confidence": ex.overall_confidence,
        "fields": fields,
        "line_items": line_items,
        "concerns": concerns,
        "has_blocking": any(c["severity"] == "blocking" for c in concerns),
        "journal_lines": journal_lines,
        "vendor": proposed.vendor,
        "invoice_number": proposed.invoice_number,
        "invoice_date": proposed.invoice_date,
        "amount_gross": proposed.amount_gross,
        "currency": proposed.currency,
        "kostenplaats": proposed.kostenplaats,
        "raw_text": record.raw_text,
    }


@router.get("/runs/{run_id}/status")
def run_status(run_id: str):
    s = store.get(run_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Run niet gevonden")
    return _serialise_run(run_id)
