import json

import config
from core.llm import call_llm, extract_json
from core.models import Concern, ExtractionResult, FieldValue, InvoiceRecord, TenantConfig
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

Naast de velden hierboven ook de individuele factuurregels als gestructureerde array:

| Veld in line_items | Type        | Omschrijving                                         |
|--------------------|-------------|------------------------------------------------------|
| description        | string      | Omschrijving van de regel                            |
| quantity           | float|null  | Aantal, null als niet vermeld                        |
| unit_price         | float|null  | Stukprijs excl. BTW, null als niet vermeld           |
| amount             | float       | Regelbedrag excl. BTW                                |
| vat_rate           | float|null  | BTW-tarief als decimaal (0.21), null als onbekend    |

Als de factuur geen gespecificeerde regels heeft maar alleen een totaalbedrag: maak één regel met de hoofdomschrijving.

---

## Agent-concerns

Meld actief wanneer je twijfelt of wanneer iets opvallend is.
Genereer een concern in deze gevallen:
- Een verplicht veld is null of ontbreekt geheel op de factuur
- Een bedrag is ongebruikelijk hoog of laag voor dit type leverancier
- De leveranciersnaam is ambigu of gedeeltelijk leesbaar
- Er zijn aanwijzingen van een duplicaat (zelfde factuurnummer als een eerder voorbeeld)
- Je hebt een account_code gesuggereerd maar twijfelt aan de categorisatie
- De factuur bevat tegenstrijdige informatie (bijv. BTW-bedrag klopt niet met tarief × net)

Severity:
- "info"     : opmerking, geen actie vereist, approve is mogelijk
- "warning"  : operator moet controleren, approve is mogelijk
- "blocking" : approve is niet verantwoord zonder menselijke verificatie

BELANGRIJK: een concern vervangt nooit een null-waarde.
Als je een veld niet kunt bepalen: zet value op null én genereer een blocking concern.
Genereer maximaal 5 concerns; prioriteer blocking boven warning boven info.

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
  "agent_concerns": [
    {{
      "field": "suggested_account_code",
      "severity": "warning",
      "reason": "Geen expliciete kostensoort vermeld; heb default 4000 gekozen",
      "suggested_next_steps": ["Controleer of leverancier onder verzendkosten valt (4350)"]
    }}
  ]
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


def _parse_concerns(raw_concerns: list[dict], source: str = "agent") -> list[Concern]:
    concerns = []
    for c in raw_concerns:
        concerns.append(Concern(
            field=c.get("field"),
            severity=c.get("severity", "info"),
            reason=c.get("reason", ""),
            suggested_next_steps=c.get("suggested_next_steps", []),
            source=source,
        ))
    return concerns


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

    # Support legacy uncertainty_notes: convert to a single info concern
    agent_concerns = _parse_concerns(parsed.get("agent_concerns", []))
    if not agent_concerns and parsed.get("uncertainty_notes"):
        agent_concerns = [Concern(
            field=None,
            severity="info",
            reason=parsed["uncertainty_notes"],
            source="agent",
        )]

    return ExtractionResult(
        fields=fields,
        overall_confidence=float(parsed.get("overall_confidence", 0.0)),
        agent_concerns=agent_concerns,
        system_prompt=system,
        user_prompt=user,
        llm_response_raw=raw_response,
    )
