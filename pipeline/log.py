import json
from dataclasses import asdict
from pathlib import Path

import config
from core.models import InvoiceRecord, RunLog


def init_run_log(record: InvoiceRecord) -> RunLog:
    return RunLog(
        run_id=record.run_id,
        source_file=record.source_file,
        tenant_slug=record.tenant_slug,
        created_at=record.created_at,
        final_status=record.status,
        steps={},
    )


def log_step(run_log: RunLog, step: str, data: dict) -> None:
    run_log.steps[step] = data


def save_run_log(run_log: RunLog) -> Path:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RUNS_DIR / f"{run_log.run_id}.json"

    payload = {
        "run_id": run_log.run_id,
        "source_file": run_log.source_file,
        "tenant_slug": run_log.tenant_slug,
        "created_at": run_log.created_at,
        "final_status": run_log.final_status,
        "steps": run_log.steps,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
