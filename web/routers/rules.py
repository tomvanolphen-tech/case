from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core import tenant as tenant_io

router = APIRouter()


class RuleUpdateRequest(BaseModel):
    rule_text: str


@router.get("/tenants/{slug}/rules")
def list_rules(slug: str):
    if slug not in tenant_io.list_tenants():
        raise HTTPException(status_code=404, detail="Tenant niet gevonden")
    tenant_config = tenant_io.load_tenant_config(slug)
    rules = tenant_io.list_rules(slug)
    return {
        "tenant_name": tenant_config.name,
        "rules": [
            {
                "number": r.number,
                "date": r.date,
                "run_id": r.run_id,
                "scope": r.scope,
                "scope_value": r.scope_value,
                "rule_text": r.rule_text,
            }
            for r in rules
        ],
    }


@router.put("/tenants/{slug}/rules/{number}")
def update_rule(slug: str, number: int, req: RuleUpdateRequest):
    if slug not in tenant_io.list_tenants():
        raise HTTPException(status_code=404, detail="Tenant niet gevonden")
    ok = tenant_io.update_rule(slug, number, req.rule_text)
    if not ok:
        raise HTTPException(status_code=404, detail="Regel niet gevonden")
    return {"status": "updated"}


@router.delete("/tenants/{slug}/rules/{number}")
def delete_rule(slug: str, number: int):
    if slug not in tenant_io.list_tenants():
        raise HTTPException(status_code=404, detail="Tenant niet gevonden")
    ok = tenant_io.delete_rule(slug, number)
    if not ok:
        raise HTTPException(status_code=404, detail="Regel niet gevonden")
    return {"status": "deleted"}
