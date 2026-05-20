from fastapi import APIRouter, HTTPException
from core import tenant as tenant_io
from web.mailbox_data import EMAILS, get_email

router = APIRouter()


@router.get("/inbox")
def list_inbox():
    return {
        "emails": [e.to_dict() for e in EMAILS],
        "tenants": sorted(tenant_io.list_tenants()),
    }


@router.get("/inbox/{email_id}")
def get_inbox_email(email_id: str):
    email = get_email(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="E-mail niet gevonden")
    return email.to_dict(include_raw=True)
