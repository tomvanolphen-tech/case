from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldValue:
    value: Any
    confidence: float


@dataclass
class ExtractionResult:
    fields: dict[str, FieldValue]
    overall_confidence: float
    uncertainty_notes: str
    system_prompt: str = ""
    user_prompt: str = ""
    llm_response_raw: str = ""


@dataclass
class TenantConfig:
    slug: str
    name: str
    vat_number: str
    default_currency: str
    required_fields: list[str]
    confidence_threshold: float
    account_mapping: dict[str, Any]


@dataclass
class ValidationIssue:
    field: str
    reason: str
    severity: str  # "warning" | "error"


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class JournalLine:
    side: str   # "D" | "C"
    account: str
    amount: float
    description: str


@dataclass
class ProposedBooking:
    journal_lines: list[JournalLine]
    vendor: str
    invoice_number: str
    invoice_date: str
    amount_gross: float
    currency: str


@dataclass
class ReviewOutcome:
    action: str                            # "approve" | "escalate" | "quit"
    corrections: dict[str, Any] = field(default_factory=dict)
    rules_saved: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class InvoiceRecord:
    run_id: str
    source_file: str
    raw_text: str
    tenant_slug: str | None
    status: str                            # new|extracted|validated|proposed|approved|booked|escalated
    extraction: ExtractionResult | None = None
    validation: ValidationResult | None = None
    proposed_booking: ProposedBooking | None = None
    review_outcome: ReviewOutcome | None = None
    escalation_reason: str | None = None
    created_at: str = ""


@dataclass
class RunLog:
    run_id: str
    source_file: str
    tenant_slug: str | None
    created_at: str
    final_status: str
    steps: dict[str, Any] = field(default_factory=dict)
