import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

import config
from core.models import RuleProposal, TenantConfig


@dataclass
class ParsedRule:
    number: int
    date: str
    run_id: str
    scope: str
    scope_value: str | None
    rule_text: str


def _tenant_dir(slug: str) -> Path:
    return config.TENANTS_DIR / slug


def load_tenant_config(slug: str) -> TenantConfig:
    path = _tenant_dir(slug) / "config.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TenantConfig(
        slug=slug,
        name=data["name"],
        vat_number=data.get("vat_number", ""),
        default_currency=data.get("default_currency", "EUR"),
        required_fields=data.get("required_fields", []),
        confidence_threshold=data.get("confidence_threshold", config.DEFAULT_CONFIDENCE_THRESHOLD),
        account_mapping=data.get("account_mapping", {}),
    )


def load_learned_rules(slug: str) -> str:
    path = _tenant_dir(slug) / "learned_rules.md"
    if not path.exists():
        return "(Geen geleerde regels)"
    return path.read_text(encoding="utf-8").strip()


def load_recent_examples(slug: str, n: int = config.FEW_SHOT_EXAMPLES_COUNT) -> list[dict]:
    path = _tenant_dir(slug) / "examples.jsonl"
    if not path.exists():
        return []
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    entries = [json.loads(l) for l in lines]
    entries.sort(key=lambda e: e.get("added_at", ""), reverse=True)
    return entries[:n]


def append_example(slug: str, entry: dict) -> None:
    path = _tenant_dir(slug) / "examples.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_rule(slug: str, proposal: RuleProposal, run_id: str) -> None:
    path = _tenant_dir(slug) / "learned_rules.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# Geleerde regels voor {slug}\n"
    count = existing.count("## Regel")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scope_line = f"**Scope:** {proposal.scope}" + (f" — {proposal.scope_value}" if proposal.scope_value else "")
    new_rule = (
        f"\n## Regel {count + 1} — {date_str} (run: {run_id})\n"
        f"{scope_line}\n"
        f"{proposal.rule_text}\n"
    )
    path.write_text(existing.rstrip() + new_rule, encoding="utf-8")


def list_tenants() -> list[str]:
    if not config.TENANTS_DIR.exists():
        return []
    return [d.name for d in config.TENANTS_DIR.iterdir() if d.is_dir()]


def list_rules(slug: str) -> list[ParsedRule]:
    """Parse learned_rules.md into a list of structured rule objects."""
    path = _tenant_dir(slug) / "learned_rules.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=## Regel \d+)", text)
    rules = []
    for block in blocks:
        block = block.strip()
        if not block.startswith("## Regel"):
            continue
        header_match = re.match(
            r"## Regel (\d+) — (\d{4}-\d{2}-\d{2}) \(run: ([^)]+)\)", block
        )
        if not header_match:
            continue
        number = int(header_match.group(1))
        date = header_match.group(2)
        run_id = header_match.group(3)
        lines = block.splitlines()
        scope_line = next((l for l in lines if l.startswith("**Scope:**")), "")
        scope_match = re.match(r"\*\*Scope:\*\* (\w+)(?:\s+—\s+(.+))?", scope_line)
        scope = scope_match.group(1) if scope_match else "tenant"
        scope_value = scope_match.group(2).strip() if scope_match and scope_match.group(2) else None
        rule_lines = [
            l for l in lines
            if l and not l.startswith("## Regel") and not l.startswith("**Scope:**")
        ]
        rule_text = " ".join(rule_lines).strip()
        rules.append(ParsedRule(
            number=number, date=date, run_id=run_id,
            scope=scope, scope_value=scope_value, rule_text=rule_text,
        ))
    return rules


def delete_rule(slug: str, rule_number: int) -> bool:
    """Delete rule by number and renumber remaining rules. Returns True if found."""
    rules = list_rules(slug)
    rules_to_keep = [r for r in rules if r.number != rule_number]
    if len(rules_to_keep) == len(rules):
        return False
    _rewrite_rules(slug, rules_to_keep)
    return True


def update_rule(slug: str, rule_number: int, new_text: str) -> bool:
    """Replace the rule text of a specific rule. Returns True if found."""
    rules = list_rules(slug)
    for rule in rules:
        if rule.number == rule_number:
            rule.rule_text = new_text.strip()
            _rewrite_rules(slug, rules)
            return True
    return False


def _rewrite_rules(slug: str, rules: list[ParsedRule]) -> None:
    """Rewrite learned_rules.md from a list of parsed rules, renumbering from 1."""
    path = _tenant_dir(slug) / "learned_rules.md"
    tenant_name = slug
    try:
        cfg = load_tenant_config(slug)
        tenant_name = cfg.name
    except Exception:
        pass
    lines = [f"# Geleerde regels voor {tenant_name}\n"]
    for i, rule in enumerate(rules, 1):
        scope_line = f"**Scope:** {rule.scope}" + (f" — {rule.scope_value}" if rule.scope_value else "")
        lines.append(
            f"\n## Regel {i} — {rule.date} (run: {rule.run_id})\n"
            f"{scope_line}\n"
            f"{rule.rule_text}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")
