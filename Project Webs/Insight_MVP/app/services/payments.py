from dataclasses import dataclass
from ..config import settings

@dataclass
class PaymentResult:
    provider: str
    status: str
    external_reference: str | None
    is_real_funds: bool

class PaymentComplianceError(RuntimeError):
    pass

def create_hold(amount_cents: int, currency: str, case_id: int) -> PaymentResult:
    if amount_cents <= 0:
        raise ValueError("Amount must be positive.")
    if settings.payments_mode == "demo":
        return PaymentResult("demo", "demo_pledged", f"demo-case-{case_id}", False)
    if settings.payments_mode == "external":
        raise PaymentComplianceError(
            "External escrow mode requires a contracted provider integration. "
            "Do not accept or hold tenant funds until legal/compliance approval and provider onboarding are complete."
        )
    raise PaymentComplianceError("Unknown payments mode.")
