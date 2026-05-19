from abc import ABC, abstractmethod

from core.models import InvoiceRecord


class MailboxAdapter(ABC):
    @abstractmethod
    def send_escalation(self, record: InvoiceRecord, reason: str) -> None:
        """Send an escalation notification."""


class MockMailboxAdapter(MailboxAdapter):
    def send_escalation(self, record: InvoiceRecord, reason: str) -> None:
        print(f"\n[MOCK MAILBOX] Escalatie verstuurd voor run {record.run_id}")
        print(f"  Tenant : {record.tenant_slug}")
        print(f"  Bestand: {record.source_file}")
        print(f"  Reden  : {reason}")
