from datetime import datetime, timezone
from pathlib import Path

from core.models import InvoiceRecord, NormalizedInput

_EXTENSION_MAP = {
    ".txt": "plain_text",
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".xlsx": "excel",
    ".xls": "excel",
    ".csv": "excel",
    ".png": "scan",
    ".jpg": "scan",
    ".jpeg": "scan",
    ".tiff": "scan",
    ".tif": "scan",
}


def normalize_to_text(source: Path, source_type: str | None = None) -> NormalizedInput:
    """
    Converteert een brondocument naar genormaliseerde tekst voor de extractie-pipeline.

    Ondersteund:
      plain_text (.txt)  — leest bestand direct als UTF-8 tekst

    Niet geïmplementeerd — raises NotImplementedError met implementatie-instructies:
      pdf    — gebruik pdfplumber (tekstlagen) of pypdf als fallback;
               voor gescande PDFs combineren met pytesseract.
               Sla page_count op in metadata.
      html   — gebruik BeautifulSoup4; strip navigatie, headers en scripts;
               bewaar de paginatitel als metadata.
      excel  — gebruik openpyxl; converteer relevante sheets naar tab-gescheiden tekst;
               bewaar sheet_names in metadata.
      scan   — gebruik pytesseract (lokaal) of een externe OCR-API (bijv. Google Vision);
               sla ocr_confidence op in metadata.
    """
    resolved_type = source_type or _EXTENSION_MAP.get(source.suffix.lower(), "plain_text")

    if resolved_type == "plain_text":
        return _read_plain_text(source)
    elif resolved_type == "pdf":
        raise NotImplementedError(
            "PDF-ingest is nog niet geïmplementeerd.\n"
            "Aanbevolen aanpak: gebruik `pdfplumber` voor PDFs met een tekstlaag, "
            "of `pypdf` als fallback. Sla `page_count` op in metadata.\n"
            "Voor gescande PDFs: combineer met de `scan`-handler via pytesseract."
        )
    elif resolved_type == "html":
        raise NotImplementedError(
            "HTML-ingest is nog niet geïmplementeerd.\n"
            "Aanbevolen aanpak: gebruik `beautifulsoup4` (bs4) met `html.parser`; "
            "strip navigatie-elementen, scripts en stylesheets. "
            "Bewaar de `<title>` als metadata['title']."
        )
    elif resolved_type == "excel":
        raise NotImplementedError(
            "Excel-ingest is nog niet geïmplementeerd.\n"
            "Aanbevolen aanpak: gebruik `openpyxl`; converteer relevante werkbladen "
            "naar tab-gescheiden platte tekst. Bewaar sheet-namen in metadata['sheet_names']."
        )
    elif resolved_type == "scan":
        raise NotImplementedError(
            "Scan/afbeelding-ingest is nog niet geïmplementeerd.\n"
            "Aanbevolen aanpak: gebruik `pytesseract` met Tesseract-OCR voor lokale verwerking, "
            "of een externe OCR-API (bijv. Google Cloud Vision, Azure Form Recognizer). "
            "Sla `ocr_confidence` op in metadata."
        )
    else:
        raise NotImplementedError(
            f"Bestandstype '{resolved_type}' wordt niet herkend. "
            f"Ondersteund: plain_text. Gebruik --source-type om het type expliciet op te geven."
        )


def _read_plain_text(source: Path) -> NormalizedInput:
    text = source.read_text(encoding="utf-8")
    return NormalizedInput(
        text=text,
        source_file=str(source),
        source_type="plain_text",
        metadata={"encoding": "utf-8", "size_bytes": source.stat().st_size},
    )


def ingest(file_path: str | Path, source_type: str | None = None) -> InvoiceRecord:
    path = Path(file_path)
    normalized = normalize_to_text(path, source_type=source_type)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%d-%H%M%S") + f"-{path.stem}"
    return InvoiceRecord(
        run_id=run_id,
        source_file=str(path),
        source_type=normalized.source_type,
        raw_text=normalized.text,
        tenant_slug=None,
        status="new",
        created_at=now.isoformat(),
    )
