import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import config
from core.models import ProposedBooking


@dataclass
class BookingRequest:
    """Represents the JSON body of POST /invoices."""
    vendor: str
    invoice_number: str
    invoice_date: str
    amount_gross: float
    currency: str
    journal_lines: list[dict]
    line_items: list[dict]
    kostenplaats: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "vendor": self.vendor,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "amount_gross": self.amount_gross,
            "currency": self.currency,
            "journal_lines": self.journal_lines,
            "line_items": self.line_items,
            "kostenplaats": self.kostenplaats,
            "metadata": self.metadata,
        }


@dataclass
class BookingResponse:
    """Represents the JSON response of POST /invoices."""
    status_code: int
    booking_id: str | None
    message: str
    timestamp: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class BookkeepingAdapter(ABC):
    @abstractmethod
    def book(self, proposed: ProposedBooking) -> str:
        """Submit a booking. Returns booking_id. Raises on error."""

    @abstractmethod
    def env(self) -> str:
        """Returns the target environment: 'test' or 'prod'."""


class MockBookkeepingAdapter(BookkeepingAdapter):
    """
    Simulates POST /invoices against a bookkeeping REST API.

    Contract:
      Request : POST {base_url}/invoices  (BookingRequest as JSON body)
      Response: 201 Created               {"booking_id": "...", "message": "ok", "timestamp": "..."}
      Errors  : 422 Unprocessable Entity  if amount_gross <= 0
                500 Internal Server Error simulated on request if MOCK_FORCE_ERROR=1
    """

    def __init__(self, target_env: str | None = None) -> None:
        self._env = target_env or config.BOOKKEEPING_ENV
        self._base_url = config.bookkeeping_api_url(self._env)

    def env(self) -> str:
        return self._env

    def book(self, proposed: ProposedBooking) -> str:
        request = BookingRequest(
            vendor=proposed.vendor,
            invoice_number=proposed.invoice_number,
            invoice_date=proposed.invoice_date,
            amount_gross=proposed.amount_gross,
            currency=proposed.currency,
            journal_lines=[
                {"side": l.side, "account": l.account, "amount": l.amount, "description": l.description}
                for l in proposed.journal_lines
            ],
            line_items=[
                {
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": li.unit_price,
                    "amount": li.amount,
                    "vat_rate": li.vat_rate,
                }
                for li in proposed.line_items
            ],
            kostenplaats=proposed.kostenplaats,
            metadata={"env": self._env, "submitted_at": _now()},
        )

        response = self._simulate_post(request)

        if not response.ok:
            raise BookingError(
                f"Boeking mislukt [{response.status_code}]: {response.message}\n"
                f"URL: POST {self._base_url}/invoices"
            )

        self._save_audit(request, response)
        return response.booking_id

    def _simulate_post(self, request: BookingRequest) -> BookingResponse:
        """Simulates the HTTP round-trip without making real network calls."""
        # 422: invalid payload
        if request.amount_gross <= 0:
            return BookingResponse(
                status_code=422,
                booking_id=None,
                message=f"amount_gross must be > 0, got {request.amount_gross}",
                timestamp=_now(),
            )

        # 500: forced error via env var (for testing error paths)
        import os
        if os.getenv("MOCK_FORCE_ERROR") == "1":
            return BookingResponse(
                status_code=500,
                booking_id=None,
                message="Internal server error (MOCK_FORCE_ERROR=1)",
                timestamp=_now(),
            )

        # 201: success
        booking_id = f"BOOK-{self._env.upper()}-{int(time.time())}"
        return BookingResponse(
            status_code=201,
            booking_id=booking_id,
            message="Invoice booked successfully",
            timestamp=_now(),
        )

    def _save_audit(self, request: BookingRequest, response: BookingResponse) -> None:
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        audit = {
            "request": {
                "method": "POST",
                "url": f"{self._base_url}/invoices",
                "body": request.to_dict(),
            },
            "response": {
                "status_code": response.status_code,
                "booking_id": response.booking_id,
                "message": response.message,
                "timestamp": response.timestamp,
            },
        }
        path = config.RUNS_DIR / f"{response.booking_id}.json"
        path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


class BookingError(Exception):
    pass


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
