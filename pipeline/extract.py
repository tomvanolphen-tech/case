import json

import config
from core.llm import call_llm, extract_json
from core.models import ExtractionResult, FieldValue, InvoiceRecord, TenantConfig
from core import tenant as tenant_io

SYSTEM_TEMPLATE = """\
Je bent een nauwkeurige financiële extractie-assistent voor administratiekantoor {tenant_name}.
Je taak: extraheer gestructureerde boekhoudkundige velden uit de aangeleverde factuurtext.

Regels:
- Geef UITSLUITEND een geldig JSON-object terug. Geen markdown, geen uitleg, geen codeblokken.
- Als je een veld niet met redelijke zekerheid kunt vaststellen: gebruik null als waarde en zet confidence <= 0.4.
- Gok nooit. Een null-waarde is beter dan een fout antwoord.
- Datums altijd als ISO 8601 (YYYY-MM-DD).
- Bedragen altijd als float, geen valutasymbolen.
- Confidence is een float tussen 0.0 en 1.0.\
"""

USER_TEMPLATE = """\
## Klantspecifieke regels voor {tenant_name}

{learned_rules_block}

---

## Voorbeelden van eerder correct verwerkte facturen

{few_shot_examples_block}

---

## Te extraheren velden

| Veld                   | Type         | Omschrijving                                                   |
|------------------------|--------------|----------------------------------------------------------------|
| vendor                 | string       | Naam van de leverancier                                        |
| invoice_number         | string       | Factuurnummer                                                  |
| invoice_date           | string       | Factuurdatum (YYYY-MM-DD)                                      |
| due_date               | string|null  | Vervaldatum (YYYY-MM-DD), null als niet vermeld                |
| amount_gross           | float        | Totaalbedrag inclusief BTW                                     |
| amount_vat             | float|null   | BTW-bedrag, null als niet vermeld                              |
| vat_rate               | float|null   | BTW-tarief als decimaal (bijv. 0.21), null als onbekend        |
| amount_net             | float|null   | Totaal exclusief BTW, null als niet te berekenen               |
| currency               | string       | Valutacode (bijv. EUR)                                         |
| description            | string       | Korte omschrijving van geleverde dienst of product             |
| suggested_account_code | string|null  | Grootboekrekeningnummer o.b.v. klantregels, null als onbekend  |

---

## Factuurtext

```
{raw_invoice_text}
```

---

## Verwacht outputformaat (strikt JSON, geen markdown, geen uitleg)

{{
  "fields": {{
    "vendor":                 {{"value": "...",  "confidence": 0.0}},
    "invoice_number":         {{"value": "...",  "confidence": 0.0}},
    "invoice_date":           {{"value": "...",  "confidence": 0.0}},
    "due_date":               {{"value": null,   "confidence": 0.0}},
    "amount_gross":           {{"value": 0.0,    "confidence": 0.0}},
    "amount_vat":             {{"value": null,   "confidence": 0.0}},
    "vat_rate":               {{"value": null,   "confidence": 0.0}},
    "amount_net":             {{"value": null,   "confidence": 0.0}},
    "currency":               {{"value": "EUR",  "confidence": 0.0}},
    "description":            {{"value": "...",  "confidence": 0.0}},
    "suggested_account_code": {{"value": null,   "confidence": 0.0}}
  }},
  "overall_confidence": 0.0,
  "uncertainty_notes": "Korte toelichting bij eventuele twijfels of ontbrekende informatie."
}}\
"""


def _format_examples(examples: list[dict]) -> str:
    if not examples:
        return "(Geen voorbeelden beschikbaar)"
    parts = []
    for i, ex in enumerate(examples, 1):
        inp = ex.get("input", {})
        out = ex.get("output", {})
        note = ex.get("operator_note", "")
        parts.append(
            f"Voorbeeld {i}:\n"
            f"Input: {json.dumps(inp, ensure_ascii=False)}\n"
            f"Correcte output: {json.dumps(out, ensure_ascii=False)}\n"
            f"Operatornoot: {note}"
        )
    return "\n\n".join(parts)


def build_extract_prompt(
    raw_text: str,
    tenant_config: TenantConfig,
    rules: str,
    examples: list[dict],
) -> tuple[str, str]:
    system = SYSTEM_TEMPLATE.format(tenant_name=tenant_config.name)
    user = USER_TEMPLATE.format(
        tenant_name=tenant_config.name,
        learned_rules_block=rules,
        few_shot_examples_block=_format_examples(examples),
        raw_invoice_text=raw_text,
    )
    return system, user


def extract(record: InvoiceRecord, tenant_config: TenantConfig) -> ExtractionResult:
    rules = tenant_io.load_learned_rules(tenant_config.slug)
    examples = tenant_io.load_recent_examples(tenant_config.slug, config.FEW_SHOT_EXAMPLES_COUNT)

    system, user = build_extract_prompt(record.raw_text, tenant_config, rules, examples)
    raw_response = call_llm(system=system, user=user)
    parsed = extract_json(raw_response)

    fields: dict[str, FieldValue] = {}
    for field_name, field_data in parsed.get("fields", {}).items():
        fields[field_name] = FieldValue(
            value=field_data.get("value"),
            confidence=float(field_data.get("confidence", 0.0)),
        )

    return ExtractionResult(
        fields=fields,
        overall_confidence=float(parsed.get("overall_confidence", 0.0)),
        uncertainty_notes=parsed.get("uncertainty_notes", ""),
        system_prompt=system,
        user_prompt=user,
        llm_response_raw=raw_response,
    )
