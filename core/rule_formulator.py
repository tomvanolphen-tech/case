import json
from typing import Any

from core.llm import call_llm, extract_json, LLMParseError
from core.models import ConflictCheckResult, RuleProposal

_FORMULATE_SYSTEM = """\
Je helpt een boekhoudkantoor herbruikbare verwerkingsregels formuleren op basis van operator-correcties.
Een goede regel:
- Is generiek genoeg om op meerdere toekomstige facturen toe te passen
- Noemt GEEN specifieke factuurbedragen, -nummers of -datums
- Is geschreven in natuurlijke taal, begrijpelijk voor een niet-technische operator
- Heeft een duidelijke scope: vendor (geldt voor alle facturen van deze leverancier bij deze klant)
  of tenant (geldt voor alle facturen van deze klant, ongeacht leverancier)

Geef ALLEEN een geldig JSON-object terug. Geen markdown, geen uitleg.\
"""

_FORMULATE_USER = """\
## Factuurtext
{raw_invoice_text}

## Wat de agent zelf extraheerde
{original_extraction_json}

## Operator-correctie
Veld     : {field_name}
Oud      : {old_value}
Nieuw    : {new_value}
Notitie  : {operator_note}

## Verwacht outputformaat (strikt JSON)
{{
  "rule_text": "Facturen van [vendor] worden altijd geboekt op rekening [X] omdat [reden].",
  "scope": "vendor",
  "scope_value": "[vendor naam of null]",
  "generalization_warning": null
}}

Vul generalization_warning in als de regel te specifiek lijkt voor één factuur
(bijv. als de correctie bedrag-specifiek is of eenmalig lijkt).\
"""

_CONFLICT_SYSTEM = """\
Je controleert of een nieuwe boekhoudkregel conflicteert met bestaande regels.
Een conflict bestaat wanneer twee regels voor dezelfde situatie een andere uitkomst voorschrijven.
Geef ALLEEN een geldig JSON-object terug.\
"""

_CONFLICT_USER = """\
## Nieuwe regel
{new_rule_text}

## Bestaande regels
{existing_rules_md}

## Verwacht outputformaat (strikt JSON)
{{
  "has_conflict": false,
  "conflicting_rules": [],
  "explanation": ""
}}\
"""


def formulate_rule(
    raw_text: str,
    original_extraction: dict,
    field_name: str,
    old_value: Any,
    new_value: Any,
    operator_note: str,
    vendor_name: str,
) -> RuleProposal:
    user = _FORMULATE_USER.format(
        raw_invoice_text=raw_text[:800],
        original_extraction_json=json.dumps(original_extraction, ensure_ascii=False),
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        operator_note=operator_note or "(geen notitie)",
    )
    try:
        raw = call_llm(system=_FORMULATE_SYSTEM, user=user)
        data = extract_json(raw)
    except LLMParseError:
        # Fallback: simple rule if LLM fails to produce valid JSON
        return RuleProposal(
            rule_text=f'Facturen van "{vendor_name}": {field_name} = {new_value}.',
            scope="vendor",
            scope_value=vendor_name,
            generalization_warning=None,
        )

    return RuleProposal(
        rule_text=data.get("rule_text", f'Facturen van "{vendor_name}": {field_name} = {new_value}.'),
        scope=data.get("scope", "vendor"),
        scope_value=data.get("scope_value"),
        generalization_warning=data.get("generalization_warning"),
    )


def check_rule_conflicts(new_rule: str, existing_rules_md: str) -> ConflictCheckResult:
    if not existing_rules_md.strip() or existing_rules_md.strip() == "(Geen geleerde regels)":
        return ConflictCheckResult(has_conflict=False)

    user = _CONFLICT_USER.format(
        new_rule_text=new_rule,
        existing_rules_md=existing_rules_md,
    )
    try:
        raw = call_llm(system=_CONFLICT_SYSTEM, user=user)
        data = extract_json(raw)
    except LLMParseError:
        # On parse failure: assume no conflict (fail-open for MVP)
        return ConflictCheckResult(has_conflict=False, explanation="Conflictcheck kon niet worden uitgevoerd (parse error)")

    return ConflictCheckResult(
        has_conflict=bool(data.get("has_conflict", False)),
        conflicting_rules=data.get("conflicting_rules", []),
        explanation=data.get("explanation", ""),
    )
