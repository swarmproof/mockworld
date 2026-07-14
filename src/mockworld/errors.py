"""First-class errors and the handler ``Result`` type (ARCHITECTURE §4.2).

Faults are domain objects with realistic, vendor-shaped bodies — not error
strings — so an agent misclassifying a ``card_declined`` as a network error is a
bug the mock can actually surface (REQ-FAULT-2, REQ-RT-11). Mocks reference these
by name; a mock may register custom errors at load time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# name -> template. `body` fields are merged with per-call overrides; {slots}
# in strings are filled from the same overrides.
_ERROR_LIBRARY: dict[str, dict[str, Any]] = {
    # --- payments (Stripe-shaped) ---
    "card_declined": {
        "http_status": 402,
        "body": {
            "type": "card_error",
            "code": "card_declined",
            "decline_code": "generic_decline",
            "message": "Your card was declined.",
        },
    },
    "insufficient_funds": {
        "http_status": 402,
        "body": {
            "type": "card_error",
            "code": "card_declined",
            "decline_code": "insufficient_funds",
            "message": "Your card has insufficient funds.",
        },
    },
    "resource_missing": {
        "http_status": 404,
        "body": {
            "type": "invalid_request_error",
            "code": "resource_missing",
            "message": "No such resource.",
        },
    },
    "refund_exceeds_charge": {
        "http_status": 400,
        "body": {
            "type": "invalid_request_error",
            "code": "refund_exceeds_charge",
            "message": "Refund amount exceeds the remaining captured amount.",
        },
    },
    "charge_already_refunded": {
        "http_status": 400,
        "body": {
            "type": "invalid_request_error",
            "code": "charge_already_refunded",
            "message": "This charge has already been fully refunded.",
        },
    },
    "dispute": {
        "http_status": 402,
        "body": {
            "type": "card_error",
            "code": "dispute",
            "message": "This charge has been disputed by the cardholder.",
        },
    },
    # --- shared transport-shaped business fault ---
    "rate_limited": {
        "http_status": 429,
        "retry_after_s": 2,
        "body": {
            "type": "rate_limit_error",
            "code": "rate_limited",
            "message": "Too many requests. Please retry after the indicated delay.",
        },
    },
    # --- crm ---
    "not_found": {
        "http_status": 404,
        "body": {"code": "not_found", "message": "Record not found."},
    },
    "permission_denied": {
        "http_status": 403,
        "body": {"code": "permission_denied", "message": "You do not have permission to perform this action."},
    },
    "stale_write": {
        "http_status": 409,
        "body": {
            "code": "stale_write",
            "message": "The record was modified since you last read it (optimistic-lock conflict).",
        },
    },
    # --- exchange ---
    "slippage_exceeded": {
        "http_status": 400,
        "body": {
            "code": "slippage_exceeded",
            "message": "Fill price moved beyond the allowed slippage tolerance; order rejected.",
        },
    },
    "market_halted": {
        "http_status": 503,
        "body": {"code": "market_halted", "message": "Trading on this market is currently halted."},
    },
    # --- email ---
    "hard_bounce": {
        "http_status": 400,
        "body": {"code": "hard_bounce", "message": "The recipient address permanently rejected the message."},
    },
    "spam_rejected": {
        "http_status": 400,
        "body": {"code": "spam_rejected", "message": "The message was rejected as spam."},
    },
    # --- files ---
    "access_denied": {
        "http_status": 403,
        "body": {"code": "AccessDenied", "message": "Access denied for the requested object."},
    },
    # --- generic ---
    "malformed_response": {
        "http_status": 200,
        "body": {"code": "malformed_response", "message": "(intentionally malformed payload)"},
    },
    "partial_outage": {
        "http_status": 503,
        "body": {"code": "service_unavailable", "message": "This operation is temporarily unavailable."},
    },
}


@dataclass
class MockError:
    code: str
    message: str
    http_status: int
    body: dict[str, Any]
    retry_after_s: int | None = None

    def to_payload(self) -> dict[str, Any]:
        """The agent-facing error envelope returned over MCP."""
        payload: dict[str, Any] = {"error": self.body}
        if self.retry_after_s is not None:
            payload["retry_after"] = self.retry_after_s
        return payload


def register_error(name: str, template: dict[str, Any]) -> None:
    """Register a mock-specific error template (called by the loader)."""
    _ERROR_LIBRARY[name] = template


def build_error(code: str, message: str | None = None, **overrides: Any) -> MockError:
    """Instantiate a named error, or a bare custom error if unknown."""
    template = _ERROR_LIBRARY.get(code)
    if template is None:
        body = {"code": code, "message": message or code, **overrides}
        return MockError(code=code, message=message or code, http_status=400, body=body)

    body = dict(template["body"])
    body.update(overrides)
    if message is not None:
        body["message"] = message
    return MockError(
        code=code,
        message=body.get("message", code),
        http_status=template.get("http_status", 400),
        body=body,
        retry_after_s=template.get("retry_after_s"),
    )


@dataclass
class Result:
    """A handler's return value: success data or a first-class error.

    The engine (not the handler) is responsible for tracing and for translating a
    failed result into a structured, agent-legible MCP response.
    """

    success: bool
    data: Any = None
    err: MockError | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any = None, **meta: Any) -> "Result":
        return cls(success=True, data=data, meta=meta)

    @classmethod
    def error(cls, code: str, message: str | None = None, **overrides: Any) -> "Result":
        return cls(success=False, err=build_error(code, message, **overrides))

    @classmethod
    def from_error(cls, error: MockError) -> "Result":
        return cls(success=False, err=error)
