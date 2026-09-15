import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ..config import settings

RULE_DIR = Path(__file__).resolve().parent.parent / "legal_rules"

def load_rules():
    path = RULE_DIR / settings.legal_ruleset
    return json.loads(path.read_text(encoding="utf-8"))

def compute_deadline(severity: str, created_at: datetime | None = None):
    rules = load_rules()
    hours = rules["deadlines_hours"].get(severity, rules["deadlines_hours"]["standard"])
    created_at = created_at or datetime.now(timezone.utc)
    return created_at + timedelta(hours=hours)

def render_notice(case):
    rules = load_rules()
    today = datetime.now(timezone.utc).date().isoformat()
    return rules["notice_template"].format(
        today=today,
        landlord_name=case.property.landlord.full_name,
        address=case.property.address,
        title=case.title,
        created_at=case.created_at.isoformat(),
        description=case.description,
        deadline_at=case.deadline_at.isoformat() if case.deadline_at else "Not configured",
        case_id=case.id,
    ), rules["id"], rules["disclaimer"]
