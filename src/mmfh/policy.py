"""Policy: broker pre-filter and the signed request context forwarded to sources.

Two-stage enforcement: the broker decides which sources to ask at all
(pre-filter, for efficiency); each source decides whether to answer and what
to redact (enforcement). The broker never overrides a source decision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from .catalogue import Catalogue
from .models import LogicalInformationRequest

# Demonstrator-only signing key. A real deployment would use token exchange
# (e.g. OAuth 2.0 token exchange with SMART-style scopes) and managed keys.
_DEMO_KEY = b"mmfh-demonstrator-not-a-secret"


@dataclass(frozen=True)
class PreFilterDecision:
    source: str
    allowed: bool
    reason: str


def pre_filter(catalogue: Catalogue, lir: LogicalInformationRequest, source_id: str) -> PreFilterDecision:
    src = catalogue.sources[source_id]
    accepted = src["capability"]["purposes_accepted"]
    if lir.purpose not in accepted:
        return PreFilterDecision(
            source_id,
            False,
            f"Purpose '{lir.purpose}' not accepted by source (accepts: {', '.join(accepted)})",
        )
    return PreFilterDecision(source_id, True, "Purpose accepted")


def request_context(lir: LogicalInformationRequest, request_id: str) -> dict[str, Any]:
    """Signed context each source receives so it can apply its own rules."""
    body = {
        "request_id": request_id,
        "requester": lir.requester.model_dump(),
        "purpose": lir.purpose,
        "legal_basis": "demo: direct care" if lir.purpose == "direct-care" else f"demo: {lir.purpose}",
        "break_glass": lir.break_glass,
    }
    payload = json.dumps(body, sort_keys=True).encode()
    body["signature"] = hmac.new(_DEMO_KEY, payload, hashlib.sha256).hexdigest()
    return body


def verify_context(ctx: dict[str, Any]) -> bool:
    body = {k: v for k, v in ctx.items() if k != "signature"}
    payload = json.dumps(body, sort_keys=True).encode()
    expected = hmac.new(_DEMO_KEY, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, ctx.get("signature", ""))
