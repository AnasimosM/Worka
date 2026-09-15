from datetime import datetime, timezone
from app.services.legal import compute_deadline

def test_deadline_ordering():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert compute_deadline("emergency",now) < compute_deadline("urgent",now) < compute_deadline("standard",now)
