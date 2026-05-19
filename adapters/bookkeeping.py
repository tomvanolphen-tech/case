import json
from abc import ABC, abstractmethod
from pathlib import Path

import config
from core.models import ProposedBooking


class BookkeepingAdapter(ABC):
    @abstractmethod
    def book(self, proposed: ProposedBooking) -> str:
        """Submit a booking. Returns booking_id."""


class MockBookkeepingAdapter(BookkeepingAdapter):
    def book(self, proposed: ProposedBooking) -> str:
        import time
        booking_id = f"mock-{int(time.time())}"
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        out = {
            "booking_id": booking_id,
            "vendor": proposed.vendor,
            "invoice_number": proposed.invoice_number,
            "amount_gross": proposed.amount_gross,
            "currency": proposed.currency,
            "journal_lines": [
                {"side": l.side, "account": l.account, "amount": l.amount, "description": l.description}
                for l in proposed.journal_lines
            ],
        }
        path = config.RUNS_DIR / f"{booking_id}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return booking_id
