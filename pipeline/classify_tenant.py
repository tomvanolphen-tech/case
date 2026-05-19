import sys

from core import tenant as tenant_io
from core.llm import call_llm, extract_json
from core.models import InvoiceRecord


def _validate_slug(slug: str) -> None:
    available = tenant_io.list_tenants()
    if slug not in available:
        slugs_str = ", ".join(sorted(available)) if available else "(geen tenants gevonden)"
        print(f"Fout: tenant '{slug}' bestaat niet in tenants/.")
        print(f"Beschikbare tenants: {slugs_str}")
        sys.exit(1)


def classify_tenant(record: InvoiceRecord, tenant_slug: str) -> InvoiceRecord:
    """Assign a known tenant slug to the record. Validates that the slug exists."""
    _validate_slug(tenant_slug)
    record.tenant_slug = tenant_slug
    return record


def auto_classify_tenant(record: InvoiceRecord) -> InvoiceRecord:
    """LLM-based tenant classification. Only use with --auto-classify flag."""
    print()
    print("⚠ WAARSCHUWING: automatische tenant-classificatie is actief.")
    print("  Een fout hier kan leerregels van de verkeerde klant toepassen.")

    slugs = tenant_io.list_tenants()
    if not slugs:
        print("Fout: geen tenants gevonden in tenants/.")
        sys.exit(1)

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
        "Factuurtext:\n```\n" + record.raw_text[:1000] + "\n```\n\n"
        'Geef terug: {"tenant_slug": "<slug>", "confidence": 0.0, "reason": "..."}\n'
        "Als je het niet kunt bepalen: gebruik slug null."
    )
    raw = call_llm(system=system, user=user)
    data = extract_json(raw)
    slug = data.get("tenant_slug")
    confidence = data.get("confidence", 0.0)

    if not slug or slug not in slugs:
        print("Fout: automatische classificatie kon geen tenant bepalen.")
        print(f"Beschikbare tenants: {', '.join(sorted(slugs))}")
        print("Gebruik --tenant <slug> om handmatig te specificeren.")
        sys.exit(1)

    print(f"  Gedetecteerde tenant: {slug} (confidence: {confidence:.2f})")
    print(f"  Gebruik --tenant {slug} om dit te bevestigen en deze waarschuwing te vermijden.")
    print()

    record.tenant_slug = slug
    return record
