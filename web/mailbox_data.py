from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import config

@dataclass
class MockEmail:
    id: str
    subject: str
    sender: str
    sender_name: str
    received_at: str
    attachment_filename: str
    attachment_path: str
    snippet: str
    default_tenant: str | None

    def to_dict(self, include_raw: bool = False) -> dict:
        d = {
            "id": self.id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "received_at": self.received_at,
            "attachment_filename": self.attachment_filename,
            "snippet": self.snippet,
            "default_tenant": self.default_tenant,
        }
        if include_raw:
            try:
                d["raw_text"] = Path(self.attachment_path).read_text(encoding="utf-8")
            except Exception:
                d["raw_text"] = ""
        return d


def _snippet(filename: str) -> str:
    path = config.SAMPLES_DIR / filename
    try:
        return path.read_text(encoding="utf-8")[:120].replace("\n", " ").strip()
    except Exception:
        return ""


def _path(filename: str) -> str:
    return str(config.SAMPLES_DIR / filename)


EMAILS: list[MockEmail] = [
    MockEmail(
        id="email-001",
        subject="Factuur ES-2024-00891 — Exact Software B.V.",
        sender="facturen@exactsoftware.nl",
        sender_name="Exact Software B.V.",
        received_at="2026-05-13T08:14:00Z",
        attachment_filename="invoice_001.txt",
        attachment_path=_path("invoice_001.txt"),
        snippet=_snippet("invoice_001.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-002",
        subject="Factuur PNL-2024-00142 — PostNL",
        sender="facturatie@postnl.nl",
        sender_name="PostNL B.V.",
        received_at="2026-05-14T09:02:00Z",
        attachment_filename="invoice_002.txt",
        attachment_path=_path("invoice_002.txt"),
        snippet=_snippet("invoice_002.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-003",
        subject="Factuur PNL-2024-00198 — PostNL",
        sender="facturatie@postnl.nl",
        sender_name="PostNL B.V.",
        received_at="2026-05-14T09:04:00Z",
        attachment_filename="invoice_003.txt",
        attachment_path=_path("invoice_003.txt"),
        snippet=_snippet("invoice_003.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-004",
        subject="Invoice MS-2024-00341 — Microsoft",
        sender="billing@microsoft.com",
        sender_name="Microsoft Ireland Operations Limited",
        received_at="2026-05-14T11:30:00Z",
        attachment_filename="invoice_004.txt",
        attachment_path=_path("invoice_004.txt"),
        snippet=_snippet("invoice_004.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-005",
        subject="Factuur STA-2024-00892 — Staples",
        sender="facturatie@staples.nl",
        sender_name="Staples Nederland B.V.",
        received_at="2026-05-15T10:15:00Z",
        attachment_filename="invoice_005.txt",
        attachment_path=_path("invoice_005.txt"),
        snippet=_snippet("invoice_005.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-006",
        subject="Factuur schoonmaak februari — De Glans",
        sender="admin@deglans.nl",
        sender_name="Schoonmaakbedrijf De Glans V.O.F.",
        received_at="2026-05-15T13:44:00Z",
        attachment_filename="invoice_006.txt",
        attachment_path=_path("invoice_006.txt"),
        snippet=_snippet("invoice_006.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-007",
        subject="Factuur TP-2024-00156 — Telecom Partners",
        sender="facturen@telecompartners.nl",
        sender_name="Telecom Partners B.V.",
        received_at="2026-05-16T08:55:00Z",
        attachment_filename="invoice_007.txt",
        attachment_path=_path("invoice_007.txt"),
        snippet=_snippet("invoice_007.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-008",
        subject="Factuur JDV-2024-007 — J. de Vries",
        sender="jdevries@freelance.nl",
        sender_name="J. de Vries",
        received_at="2026-05-16T14:20:00Z",
        attachment_filename="invoice_008.txt",
        attachment_path=_path("invoice_008.txt"),
        snippet=_snippet("invoice_008.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-009",
        subject="Factuur ADO-2024-00317 — Adobe Systems",
        sender="billing@adobe.com",
        sender_name="Adobe Systems B.V.",
        received_at="2026-05-17T09:10:00Z",
        attachment_filename="invoice_009.txt",
        attachment_path=_path("invoice_009.txt"),
        snippet=_snippet("invoice_009.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-010",
        subject="Factuur DHL-2024-00581 — DHL Express",
        sender="billing@dhl.nl",
        sender_name="DHL Express Netherlands B.V.",
        received_at="2026-05-17T10:30:00Z",
        attachment_filename="invoice_010.txt",
        attachment_path=_path("invoice_010.txt"),
        snippet=_snippet("invoice_010.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-011",
        subject="Invoice AWS-EU-2024-00442 — Amazon Web Services",
        sender="aws-billing@amazon.com",
        sender_name="Amazon Web Services EMEA SARL",
        received_at="2026-05-18T07:45:00Z",
        attachment_filename="invoice_betaworks_001.txt",
        attachment_path=_path("invoice_betaworks_001.txt"),
        snippet=_snippet("invoice_betaworks_001.txt"),
        default_tenant="betaworks",
    ),
    MockEmail(
        id="email-013",
        subject="Factuur GLS-2024-00724 — GLS Netherlands",
        sender="facturatie@gls-netherlands.com",
        sender_name="GLS Netherlands B.V.",
        received_at="2026-05-19T14:30:00Z",
        attachment_filename="invoice_011.txt",
        attachment_path=_path("invoice_011.txt"),
        snippet=_snippet("invoice_011.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-014",
        subject="Factuur PNL-2024-03847 — PostNL (ontbrekende rekening)",
        sender="facturatie@postnl.nl",
        sender_name="PostNL B.V.",
        received_at="2026-05-20T08:30:00Z",
        attachment_filename="invoice_012.txt",
        attachment_path=_path("invoice_012.txt"),
        snippet=_snippet("invoice_012.txt"),
        default_tenant="acme",
    ),
    MockEmail(
        id="email-012",
        subject="Factuur WSA-2024-00088 — Webdesign Studio Amsterdam",
        sender="facturatie@webdesignamsterdam.nl",
        sender_name="Webdesign Studio Amsterdam B.V.",
        received_at="2026-05-19T11:00:00Z",
        attachment_filename="invoice_html_001.html",
        attachment_path=_path("invoice_html_001.html"),
        snippet=_snippet("invoice_html_001.html"),
        default_tenant="acme",
    ),
]

EMAIL_INDEX: dict[str, MockEmail] = {e.id: e for e in EMAILS}


def get_email(email_id: str) -> MockEmail | None:
    return EMAIL_INDEX.get(email_id)
