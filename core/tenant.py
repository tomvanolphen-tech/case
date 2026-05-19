import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

import config
from core.models import TenantConfig


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


def append_rule(slug: str, rule_text: str) -> None:
    path = _tenant_dir(slug) / "learned_rules.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# Geleerde regels voor {slug}\n"
    count = existing.count("## Regel")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_rule = f"\n## Regel {count + 1} — {date_str}\n{rule_text}\n"
    path.write_text(existing.rstrip() + new_rule, encoding="utf-8")


def list_tenants() -> list[str]:
    if not config.TENANTS_DIR.exists():
        return []
    return [d.name for d in config.TENANTS_DIR.iterdir() if d.is_dir()]
