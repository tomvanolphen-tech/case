from adapters.bookkeeping import BookkeepingAdapter
from adapters.mailbox import MailboxAdapter
from core.models import InvoiceRecord, ProposedBooking


def book(proposed: ProposedBooking, adapter: BookkeepingAdapter) -> str:
    return adapter.book(proposed)


def escalate(record: InvoiceRecord, reason: str, adapter: MailboxAdapter) -> None:
    adapter.send_escalation(record, reason)
