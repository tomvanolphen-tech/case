from datetime import datetime, timezone
from pathlib import Path

from core.models import InvoiceRecord


def ocr_stub(file_path: Path) -> str:
    """Stub for OCR: reads plain-text file as-is."""
    return file_path.read_text(encoding="utf-8")


def ingest(file_path: str | Path) -> InvoiceRecord:
    path = Path(file_path)
    raw_text = ocr_stub(path)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%d-%H%M%S") + f"-{path.stem}"
    return InvoiceRecord(
        run_id=run_id,
        source_file=str(path),
        raw_text=raw_text,
        tenant_slug=None,
        status="new",
        created_at=now.isoformat(),
    )
