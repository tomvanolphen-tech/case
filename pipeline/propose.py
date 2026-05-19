from core.models import ExtractionResult, JournalLine, ProposedBooking, TenantConfig


def _resolve_account_code(result: ExtractionResult, tenant_config: TenantConfig) -> str:
    mapping = tenant_config.account_mapping
    vendors = mapping.get("vendors", {})

    vendor_val = result.fields.get("vendor")
    vendor_name = vendor_val.value if vendor_val else None

    # Priority: extracted suggestion → vendor lookup → default
    suggested = result.fields.get("suggested_account_code")
    if suggested and suggested.value:
        return str(suggested.value)
    if vendor_name and vendor_name in vendors:
        return str(vendors[vendor_name])
    return str(mapping.get("default_expense", "4000"))


def _fv(result: ExtractionResult, field_name: str, default=None):
    fv = result.fields.get(field_name)
    return fv.value if fv and fv.value is not None else default


def propose(result: ExtractionResult, tenant_config: TenantConfig) -> ProposedBooking:
    mapping = tenant_config.account_mapping
    expense_account = _resolve_account_code(result, tenant_config)
    vat_account = str(mapping.get("vat_in", "1500"))
    ap_account = str(mapping.get("accounts_payable", "1600"))

    gross = float(_fv(result, "amount_gross", 0.0))
    net = _fv(result, "amount_net")
    vat = _fv(result, "amount_vat")
    vendor = _fv(result, "vendor", "Onbekend")
    description = _fv(result, "description", "")

    # Derive net/vat if missing
    if net is not None and vat is not None:
        net = float(net)
        vat = float(vat)
    elif net is not None:
        net = float(net)
        vat = round(gross - net, 2)
    elif vat is not None:
        vat = float(vat)
        net = round(gross - vat, 2)
    else:
        # Assume 21% VAT as last resort
        net = round(gross / 1.21, 2)
        vat = round(gross - net, 2)

    journal_lines = [
        JournalLine(side="D", account=expense_account, amount=net, description=description or "Kosten"),
        JournalLine(side="D", account=vat_account, amount=vat, description="BTW te vorderen"),
        JournalLine(side="C", account=ap_account, amount=gross, description=f"Crediteuren {vendor}"),
    ]

    return ProposedBooking(
        journal_lines=journal_lines,
        vendor=vendor,
        invoice_number=_fv(result, "invoice_number", ""),
        invoice_date=_fv(result, "invoice_date", ""),
        amount_gross=gross,
        currency=_fv(result, "currency", tenant_config.default_currency),
    )
