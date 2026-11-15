"""Typed observable records. Evaluation specifications are not part of these schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal[
    "Payment", "PaymentAttempt", "Authorization", "Capture", "ProviderEvent",
    "WebhookDelivery", "ApplicationStatusObservation",
]
PaymentState = Literal["captured", "authorized", "failed", "unknown"]
Disposition = Literal["no_escalation", "check_required", "escalate"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class MoneyData(StrictModel):
    amount: str = Field(min_length=1, max_length=64)
    currency: str | None

    @field_validator("amount")
    @classmethod
    def positive_decimal(cls, value: str) -> str:
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("amount must be a finite positive decimal string") from exc
        if not number.is_finite() or number <= 0 or number > Decimal("1000000000000"):
            raise ValueError("amount must be a finite positive decimal string")
        exponent = number.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -8:
            raise ValueError("demo amounts support at most eight fractional decimal places")
        return format(number, "f")

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 3 or not value.isascii() or not value.isalpha() or value != value.upper()):
            raise ValueError("currency must be an uppercase three-letter code or null")
        return value


class PaymentData(MoneyData):
    record_type: Literal["source_context", "provider_snapshot"]
    source_transaction_id: str | None = None
    original_status: Literal["Successful", "Failed", "Pending"] | None = None
    payment_method: Literal["Debit Card", "Credit Card"] | None = None
    provider_status: Literal[
        "requires_payment_method", "requires_action", "processing", "requires_capture", "succeeded", "canceled"
    ] | None = None
    capture_history_complete: bool = Field(default=False, strict=True)
    attempt_history_complete: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validate_role(self) -> Self:
        if self.record_type == "source_context":
            if not self.source_transaction_id or not self.original_status or not self.payment_method:
                raise ValueError("source context requires original transaction ID, status, and card method")
            if self.provider_status or self.capture_history_complete or self.attempt_history_complete:
                raise ValueError("source context cannot assert provider state or history completeness")
        elif self.provider_status is None:
            raise ValueError("provider snapshot requires provider_status")
        return self


class AttemptData(StrictModel):
    attempt_id: str = Field(min_length=1, max_length=160)
    status: Literal["succeeded", "failed", "processing", "requires_action"]
    error_code: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def error_is_observed_failure(self) -> Self:
        if self.error_code and self.status != "failed":
            raise ValueError("an attempt error_code requires failed status")
        return self


class AuthorizationData(MoneyData):
    authorization_id: str = Field(min_length=1, max_length=160)
    attempt_id: str | None = None
    status: Literal["authorized", "declined", "expired", "voided"]


class CaptureData(MoneyData):
    capture_id: str = Field(min_length=1, max_length=160)
    attempt_id: str | None = None
    authorization_id: str | None = None
    status: Literal["succeeded", "failed", "pending"]


class EventData(StrictModel):
    event_id: str = Field(min_length=1, max_length=160)
    event_type: Literal[
        "payment_intent.succeeded", "payment_intent.payment_failed", "payment_intent.processing",
        "payment_intent.amount_capturable_updated", "payment_intent.canceled", "charge.captured",
    ]
    subject_kind: Literal["Payment", "Authorization", "Capture"]
    subject_id: str = Field(min_length=1, max_length=160)


class DeliveryData(StrictModel):
    delivery_id: str = Field(min_length=1, max_length=160)
    event_id: str = Field(min_length=1, max_length=160)
    status: Literal["delivered", "failed", "pending"]
    http_status: int | None = Field(default=None, ge=100, le=599, strict=True)
    attempt_number: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def check_http_outcome(self) -> Self:
        if self.http_status is not None:
            success = 200 <= self.http_status < 300
            if (self.status == "delivered" and not success) or (self.status == "failed" and success):
                raise ValueError("delivery status contradicts HTTP response")
            if self.status == "pending":
                raise ValueError("pending delivery cannot have an HTTP response")
        return self


class AppData(StrictModel):
    observation_id: str = Field(min_length=1, max_length=160)
    status: Literal["succeeded", "failed", "pending", "processing", "requires_action", "authorized"]
    channel: str = Field(min_length=1, max_length=100)


class Evidence(StrictModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    payment_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    kind: Kind
    source: str = Field(min_length=1, max_length=500)
    synthetic: bool
    occurred_at: str | None = None
    observed_at: str | None = None
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)

    data_models: ClassVar[dict[str, type[StrictModel]]] = {
        "Payment": PaymentData, "PaymentAttempt": AttemptData, "Authorization": AuthorizationData,
        "Capture": CaptureData, "ProviderEvent": EventData, "WebhookDelivery": DeliveryData,
        "ApplicationStatusObservation": AppData,
    }

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def valid_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            if "T" not in value and " " not in value:
                raise ValueError("timestamp requires a time component")
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("timestamp must be ISO 8601 or null") from exc
        return value

    @model_validator(mode="after")
    def validate_kind_fields(self) -> Self:
        parsed = self.data_models[self.kind].model_validate(self.data)
        # Avoid recursive assignment validation while normalizing decimal strings/defaults.
        object.__setattr__(self, "data", parsed.model_dump())
        return self


class Payment(StrictModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    symptom: str = Field(min_length=1, max_length=2000)
    source_transaction_id: str = Field(min_length=1, max_length=160)
    original: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)

    @field_validator("original")
    @classmethod
    def source_only(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"expected", "expectations", "diagnosis", "scenario", "design", "specification", "root_cause"}
        if forbidden.intersection(value):
            raise ValueError("evaluation metadata is not observable source data")
        return value


class Finding(StrictModel):
    id: str
    text: str
    evidence_ids: list[str]
    rule_id: str


class Analysis(StrictModel):
    payment_id: str
    payment_state: PaymentState
    disposition: Disposition
    confirmed_facts: list[Finding] = Field(default_factory=list)
    discrepancies: list[Finding] = Field(default_factory=list)
    hypotheses: list[Finding] = Field(default_factory=list)
    unknowns: list[Finding] = Field(default_factory=list)
    next_checks: list[Finding] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_findings(self) -> Self:
        findings = self.confirmed_facts + self.discrepancies + self.hypotheses + self.unknowns + self.next_checks
        if len({f.id for f in findings}) != len(findings):
            raise ValueError("finding IDs must be unique within an analysis")
        return self
