from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldValue:
    value: Any
    confidence: float


@dataclass
class Concern:
    field: str | None                    # welk veld, of None voor algemeen
    severity: str                        # "info" | "warning" | "blocking"
    reason: str
    suggested_next_steps: list[str] = field(default_factory=list)
    source: str = "agent"                # "agent" | "validator"


@dataclass
class LineItem:
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float
    vat_rate: float | None


@dataclass
class ExtractionResult:
    fields: dict[str, FieldValue]
    overall_confidence: float
    line_items: list[LineItem] = field(default_factory=list)
    agent_concerns: list[Concern] = field(default_factory=list)
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
class ValidationResult:
    ok: bool                             # False als er blocking concerns zijn
    concerns: list[Concern] = field(default_factory=list)


@dataclass
class JournalLine:
    side: str                            # "D" | "C"
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
    concerns: list[Concern] = field(default_factory=list)


@dataclass
class ReviewOutcome:
    action: str                          # "approve" | "force_approve" | "escalate" | "quit"
    corrections: dict[str, Any] = field(default_factory=dict)
    rules_saved: list[str] = field(default_factory=list)
    force_approve: bool = False
    operator_confirmation: str = ""
    duration_seconds: float = 0.0


@dataclass
class InvoiceRecord:
    run_id: str
    source_file: str
    raw_text: str
    tenant_slug: str | None
    status: str                          # new|extracted|validated|proposed|approved|booked|escalated
    source_type: str = "plain_text"
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


@dataclass
class NormalizedInput:
    text: str
    source_file: str
    source_type: str                     # "plain_text" | "pdf" | "html" | "excel" | "scan"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleProposal:
    rule_text: str
    scope: str                           # "vendor" | "tenant"
    scope_value: str | None              # bijv. "PostNL B.V." voor scope=vendor
    generalization_warning: str | None


@dataclass
class ConflictCheckResult:
    has_conflict: bool
    conflicting_rules: list[str] = field(default_factory=list)
    explanation: str = ""
