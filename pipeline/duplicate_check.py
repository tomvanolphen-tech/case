import json
from pathlib import Path

import config
from core.models import Concern, ExtractionResult


def check_duplicate(extraction: ExtractionResult, current_run_id: str) -> Concern | None:
    """
    Checks existing run logs for a matching invoice_number + vendor combination.
    Returns a blocking Concern if a duplicate is found, None otherwise.
    """
    invoice_number = extraction.fields.get("invoice_number")
    vendor = extraction.fields.get("vendor")

    if not invoice_number or not invoice_number.value:
        return None

    inv_nr = str(invoice_number.value).strip()
    vendor_name = str(vendor.value).strip() if vendor and vendor.value else None

    matches = []
    for log_file in sorted(config.RUNS_DIR.glob("*.json")):
        if not log_file.stem.startswith("20"):
            continue
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if data.get("run_id") == current_run_id:
            continue

        parsed = data.get("steps", {}).get("extract", {}).get("parsed_fields", {})
        log_inv_nr = parsed.get("invoice_number", {}).get("value")
        log_vendor = parsed.get("vendor", {}).get("value")

        if log_inv_nr and str(log_inv_nr).strip() == inv_nr:
            if vendor_name is None or (log_vendor and str(log_vendor).strip() == vendor_name):
                matches.append(data["run_id"])

    if not matches:
        return None

    return Concern(
        field="invoice_number",
        severity="blocking",
        reason=f"Factuurnummer '{inv_nr}' is al eerder verwerkt in: {', '.join(matches)}",
        suggested_next_steps=[
            f"Controleer run {matches[0]} in runs/{matches[0]}.json",
            "Bevestig bij leverancier of dit een nieuwe factuur is",
            "Gebruik [fa] force-approve als boeking toch gewenst is",
        ],
        source="validator",
    )
