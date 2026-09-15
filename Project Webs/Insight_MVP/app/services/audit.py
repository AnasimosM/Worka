from ..models import AuditEvent

def log(db, action: str, actor_id=None, case_id=None, detail=""):
    event = AuditEvent(action=action, actor_id=actor_id, case_id=case_id, detail=detail)
    db.add(event)
    return event
