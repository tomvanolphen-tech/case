from __future__ import annotations
import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adapters.bookkeeping import MockBookkeepingAdapter, BookingError
from adapters.mailbox import MockMailboxAdapter
from core import tenant as tenant_io
from core.models import FieldValue, ReviewOutcome
from core.rule_formulator import formulate_rule, check_rule_conflicts
from pipeline.book_or_escalate import book, escalate
from pipeline.log import log_step, save_run_log
from pipeline.propose import propose
from web import state as store
from web.state import PipelinePhase
from web.routers.pipeline import _serialise_run

router = APIRouter()

FORCE_APPROVE_PHRASE = "JA IK NEEM VERANTWOORDELIJKHEID"


class ActionRequest(BaseModel):
    action: str
    # approve / force_approve
    confirmation: str | None = None
    # correct
    field: str | None = None
    new_value: Any = None
    note: str | None = None
    save_as_rule: bool = False
    # confirm_rule
    rule_text: str | None = None
    scope: str | None = None
    scope_value: str | None = None


@router.post("/runs/{run_id}/action")
async def review_action(run_id: str, req: ActionRequest):
    s = store.get(run_id)
    if s is None or s.phase != PipelinePhase.PROPOSED:
        raise HTTPException(status_code=404, detail="Run niet gevonden of niet gereed voor review")

    record = s.record
    proposed = record.proposed_booking
    run_log = s._run_log  # type: ignore[attr-defined]

    # ── APPROVE ──────────────────────────────────────────────────────────────
    if req.action == "approve":
        if any(c.severity == "blocking" for c in proposed.concerns):
            raise HTTPException(status_code=422, detail="blocking_concerns")
        return await _do_book(run_id, s, record, proposed, run_log, force=False)

    # ── FORCE APPROVE ────────────────────────────────────────────────────────
    if req.action == "force_approve":
        if req.confirmation != FORCE_APPROVE_PHRASE:
            raise HTTPException(
                status_code=422,
                detail={"error": "confirmation_required", "expected": FORCE_APPROVE_PHRASE},
            )
        return await _do_book(run_id, s, record, proposed, run_log, force=True,
                               confirmation=req.confirmation)

    # ── ESCALATE ─────────────────────────────────────────────────────────────
    if req.action == "escalate":
        reason = req.note or "Geëscaleerd via webinterface"
        record.escalation_reason = reason
        mailbox = MockMailboxAdapter()
        await asyncio.to_thread(escalate, record, reason, mailbox)
        record.status = "escalated"
        log_step(run_log, "review", {"status": "escalate", "operator_action": "escalate", "reason": reason})
        log_step(run_log, "book_or_escalate", {"status": "escalated", "reason": reason})
        run_log.final_status = "escalated"
        await asyncio.to_thread(save_run_log, run_log)
        store.update(run_id, phase=PipelinePhase.DONE)
        return {"status": "escalated"}

    # ── CANCEL ───────────────────────────────────────────────────────────────
    if req.action == "cancel":
        store.remove(run_id)
        return {"status": "cancelled"}

    # ── CORRECT ──────────────────────────────────────────────────────────────
    if req.action == "correct":
        if not req.field or req.new_value is None:
            raise HTTPException(status_code=422, detail="field en new_value zijn verplicht")

        ex = record.extraction
        current = ex.fields.get(req.field)
        old_value = current.value if current else None

        if req.field in ex.fields:
            ex.fields[req.field].value = req.new_value
            ex.fields[req.field].confidence = 1.0
        else:
            ex.fields[req.field] = FieldValue(value=req.new_value, confidence=1.0)

        tenant_config = await asyncio.to_thread(tenant_io.load_tenant_config, record.tenant_slug)
        updated_proposed = await asyncio.to_thread(propose, ex, record.validation, tenant_config)
        record.proposed_booking = updated_proposed

        response: dict[str, Any] = {
            "status": "corrected",
            "updated_fields": {
                k: {"value": v.value, "confidence": v.confidence}
                for k, v in ex.fields.items()
            },
            "updated_journal_lines": [
                {"side": l.side, "account": l.account, "amount": l.amount, "description": l.description}
                for l in updated_proposed.journal_lines
            ],
            "updated_concerns": [
                {
                    "field": c.field,
                    "severity": c.severity,
                    "reason": c.reason,
                    "suggested_next_steps": c.suggested_next_steps,
                    "source": c.source,
                }
                for c in updated_proposed.concerns
            ],
            "has_blocking": any(c.severity == "blocking" for c in updated_proposed.concerns),
        }

        if req.save_as_rule:
            vendor_fv = ex.fields.get("vendor")
            vendor_name = vendor_fv.value if vendor_fv else "onbekend"
            original_extraction = {
                k: {"value": v.value, "confidence": v.confidence}
                for k, v in ex.fields.items()
            }
            proposal = await asyncio.to_thread(
                formulate_rule,
                record.raw_text,
                original_extraction,
                req.field,
                old_value,
                req.new_value,
                req.note or "",
                vendor_name,
            )
            existing_rules = await asyncio.to_thread(tenant_io.load_learned_rules, record.tenant_slug)
            conflict = await asyncio.to_thread(check_rule_conflicts, proposal.rule_text, existing_rules)

            rule_proposal = {
                "rule_text": proposal.rule_text,
                "scope": proposal.scope,
                "scope_value": proposal.scope_value,
                "generalization_warning": proposal.generalization_warning,
                "has_conflict": conflict.has_conflict,
                "conflicting_rules": conflict.conflicting_rules,
                "conflict_explanation": conflict.explanation,
            }
            store.update(run_id, pending_rule={
                "field": req.field,
                "new_value": req.new_value,
                "note": req.note or "",
                "vendor_name": vendor_name,
                "proposal": proposal,
            })
            response["rule_proposal"] = rule_proposal

        return response

    # ── CONFIRM RULE ─────────────────────────────────────────────────────────
    if req.action == "confirm_rule":
        if not req.rule_text or not req.scope:
            raise HTTPException(status_code=422, detail="rule_text en scope zijn verplicht")

        pending = s.pending_rule
        if pending is None:
            raise HTTPException(status_code=422, detail="Geen openstaande regelopslag")

        from core.models import RuleProposal
        import copy
        final_proposal = copy.copy(pending["proposal"])
        final_proposal.rule_text = req.rule_text
        final_proposal.scope = req.scope
        final_proposal.scope_value = req.scope_value

        await asyncio.to_thread(tenant_io.append_rule, record.tenant_slug, final_proposal, run_id)

        ex = record.extraction
        vendor_fv = ex.fields.get("vendor")
        vendor_name = vendor_fv.value if vendor_fv else "onbekend"
        from datetime import datetime, timezone
        example_entry = {
            "id": f"ex-{run_id}",
            "added_at": datetime.now(timezone.utc).isoformat(),
            "operator_note": pending["note"] or f"{pending['field']} gecorrigeerd naar {pending['new_value']}",
            "input": {"vendor": vendor_name, "raw_snippet": record.raw_text[:200]},
            "output": {k: v.value for k, v in ex.fields.items() if v.value is not None},
        }
        await asyncio.to_thread(tenant_io.append_example, record.tenant_slug, example_entry)
        store.update(run_id, pending_rule=None)
        return {"status": "rule_saved"}

    raise HTTPException(status_code=422, detail=f"Onbekende actie: {req.action}")


async def _do_book(run_id, s, record, proposed, run_log, *, force: bool, confirmation: str = ""):
    bookkeeping = MockBookkeepingAdapter()
    try:
        booking_id, booking_audit = await asyncio.to_thread(book, proposed, bookkeeping)
    except BookingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    record.status = "booked"
    action = "force_approve" if force else "approve"
    log_step(run_log, "review", {
        "status": action,
        "operator_action": action,
        "force_approve": force,
        "operator_confirmation": confirmation,
    })
    log_step(run_log, "book_or_escalate", {"status": "booked", "booking_id": booking_id, **booking_audit})
    run_log.final_status = "booked"
    await asyncio.to_thread(save_run_log, run_log)
    store.update(run_id, phase=PipelinePhase.DONE, booking_id=booking_id)
    return {"status": "booked", "booking_id": booking_id, "force_approved": force}
