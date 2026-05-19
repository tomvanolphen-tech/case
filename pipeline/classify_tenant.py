import json

from core import tenant as tenant_io
from core.llm import call_llm, extract_json
from core.models import InvoiceRecord


def _llm_classify(raw_text: str) -> str | None:
    slugs = tenant_io.list_tenants()
    if not slugs:
        return None

    tenant_summaries = []
    for slug in slugs:
        try:
            cfg = tenant_io.load_tenant_config(slug)
            tenant_summaries.append(f"- slug: {slug}, naam: {cfg.name}, btw: {cfg.vat_number}")
        except Exception:
            tenant_summaries.append(f"- slug: {slug}")

    system = "Je bent een classificatie-assistent. Geef alleen een JSON-object terug."
    user = (
        "Bepaal op basis van de factuurtext welke tenant het beste past.\n\n"
        "Beschikbare tenants:\n" + "\n".join(tenant_summaries) + "\n\n"
        "Factuurtext:\n```\n" + raw_text[:1000] + "\n```\n\n"
        'Geef terug: {"tenant_slug": "<slug>", "confidence": 0.0, "reason": "..."}\n'
        "Als je het niet kunt bepalen: gebruik slug null."
    )
    raw = call_llm(system=system, user=user)
    data = extract_json(raw)
    slug = data.get("tenant_slug")
    return slug if slug and slug in slugs else None


def classify_tenant(record: InvoiceRecord, tenant_slug: str | None) -> InvoiceRecord:
    if tenant_slug:
        record.tenant_slug = tenant_slug
        return record

    slug = _llm_classify(record.raw_text)
    record.tenant_slug = slug
    return record
