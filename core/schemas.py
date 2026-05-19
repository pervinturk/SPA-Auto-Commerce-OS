from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import (BaseModel, ConfigDict, Field, NonNegativeFloat,
                        NonNegativeInt, PositiveFloat, PositiveInt,
                        field_validator, model_validator)


class _OmniBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=False,
        extra="forbid",
    )


class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class Severity(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class HybridRoute(str, Enum):
    LOCAL_SLM = "LOCAL_SLM"
    CLOUD     = "CLOUD"
    HYBRID    = "HYBRID"


class ShipmentStatus(str, Enum):
    PENDING  = "PENDING"
    PASSED   = "PASSED"
    BLOCKED  = "BLOCKED"
    ANDON    = "ANDON"


class ADRAction(str, Enum):
    REFUND       = "REFUND"
    REPLACE      = "REPLACE"
    PARTIAL      = "PARTIAL"
    REJECT       = "REJECT"
    ESCALATE     = "ESCALATE"
    GOODWILL     = "GOODWILL"


class IPDecision(str, Enum):
    CLEAN       = "CLEAN"
    SUSPICIOUS  = "SUSPICIOUS"
    INFRINGING  = "INFRINGING"


class InventoryDecisionIn(_OmniBase):
    sku:           str                       = Field(..., min_length=1, max_length=64)
    demand_vector: list[NonNegativeFloat]    = Field(..., min_length=1, max_length=104)
    setup_cost:    PositiveFloat
    holding_cost:  PositiveFloat
    unit_cost:     NonNegativeFloat          = 0.0
    service_level: float                     = Field(0.95, ge=0.50, le=0.9999)
    method:        str                       = Field("WAGNER_WHITIN", pattern=r"^[A-Z_]+$")

    @field_validator("demand_vector")
    @classmethod
    def _no_all_zeros(cls, v: list[float]) -> list[float]:
        if sum(v) <= 0:
            raise ValueError("demand_vector toplamı pozitif olmalı")
        return v


class InventoryDecisionOut(_OmniBase):
    id:             int
    sku:            str
    horizon:        PositiveInt
    demand_vector:  list[NonNegativeFloat]
    setup_cost:     NonNegativeFloat
    holding_cost:   NonNegativeFloat
    unit_cost:      NonNegativeFloat
    lot_sizes:      list[NonNegativeFloat]
    total_cost:     NonNegativeFloat
    order_periods:  list[NonNegativeInt]
    avg_lot_size:   NonNegativeFloat
    service_level:  float
    method:         str
    created_at:     datetime


class CarrierCandidate(_OmniBase):
    name:       str            = Field(..., min_length=1, max_length=64)
    cost:       NonNegativeFloat
    eta_days:   PositiveFloat
    damage_pct: float          = Field(..., ge=0, le=1)
    on_time:    float          = Field(..., ge=0, le=1)
    sla_pen:    NonNegativeFloat = 0.0


class CarrierSelectionIn(_OmniBase):
    order_id:    Optional[str]         = Field(None, max_length=64)
    candidates:  list[CarrierCandidate] = Field(..., min_length=2)
    weights:     list[PositiveFloat]    = Field(..., min_length=5, max_length=5)
    impact_signs: list[int]             = Field(..., min_length=5, max_length=5)

    @field_validator("weights")
    @classmethod
    def _weights_sum_one(cls, v: list[float]) -> list[float]:
        if abs(sum(v) - 1.0) > 1e-6:
            raise ValueError("weights toplamı 1.0 olmalı")
        return v

    @field_validator("impact_signs")
    @classmethod
    def _impact_pm1(cls, v: list[int]) -> list[int]:
        if any(s not in (-1, 1) for s in v):
            raise ValueError("impact_signs sadece +1 (benefit) veya -1 (cost) olabilir")
        return v


class CarrierSelectionOut(_OmniBase):
    id:               int
    order_id:         Optional[str]
    selected_carrier: str
    selected_index:   NonNegativeInt
    closeness_scores: list[float]
    ideal_best:       list[float]
    ideal_worst:      list[float]
    weights:          list[NonNegativeFloat]
    method:           str
    created_at:       datetime


class ForexPositionIn(_OmniBase):
    pair:          str             = Field(..., pattern=r"^[A-Z]{3}/[A-Z]{3}$")
    notional:      PositiveFloat
    return_series: list[float]     = Field(..., min_length=30, max_length=2520)
    horizon_days:  PositiveInt     = 10
    confidence:    float           = Field(0.99, ge=0.80, le=0.9999)
    auto_hedge_threshold_pct: float = Field(0.05, ge=0.001, le=0.50)


class ForexPositionOut(_OmniBase):
    id:                 int
    pair:               str
    notional:           NonNegativeFloat
    horizon_days:       PositiveInt
    confidence:         float
    mu_daily:           float
    sigma_daily:        NonNegativeFloat
    z_score:            float
    parametric_var:     NonNegativeFloat
    expected_shortfall: NonNegativeFloat
    hedge_recommended:  bool
    hedge_ratio:        float
    method:             str
    created_at:         datetime


class IPInfringementCheck(_OmniBase):
    listing_sku:        str             = Field(..., min_length=1, max_length=64)
    candidate_url:      Optional[str]   = Field(None, max_length=512)
    target_phash:       str             = Field(..., pattern=r"^[0-9a-fA-F]{16}$")
    candidate_phash:    str             = Field(..., pattern=r"^[0-9a-fA-F]{16}$")
    target_brand_text:  Optional[str]   = Field(None, max_length=256)
    candidate_brand_text: Optional[str] = Field(None, max_length=256)
    hamming_threshold:  PositiveInt     = 12
    tfidf_threshold:    float           = Field(0.78, ge=0, le=1)


class IPInfringementOut(_OmniBase):
    id:               int
    listing_sku:      str
    hamming_distance: NonNegativeInt
    similarity_pct:   float
    trademark_tfidf:  float
    decision:         IPDecision
    risk_level:       RiskLevel
    candidate_url:    Optional[str]
    created_at:       datetime


class ADRCaseRequest(_OmniBase):
    order_id:        str           = Field(..., min_length=1, max_length=64)
    customer_id:     Optional[str] = Field(None, max_length=64)
    dispute_type:    str           = Field(..., min_length=1, max_length=32)
    claimed_amount:  NonNegativeFloat
    evidence_score:  float         = Field(..., ge=0, le=1)
    cltv_score:      float         = Field(..., ge=0, le=1)
    repeat_risk:     float         = Field(..., ge=0, le=1)
    product_cost:    NonNegativeFloat = 0.0


class ADRCaseOut(_OmniBase):
    id:                 int
    order_id:           str
    customer_id:        Optional[str]
    dispute_type:       str
    claimed_amount:     NonNegativeFloat
    evidence_score:     float
    cltv_score:         float
    repeat_risk:        float
    decision_matrix:    dict[str, Any]
    recommended_action: ADRAction
    expected_cost:      NonNegativeFloat
    settled:            bool
    settled_at:         Optional[datetime]
    created_at:         datetime


class SensorReading(_OmniBase):
    ts:          datetime
    temperature: float
    humidity:    float          = Field(..., ge=0, le=100)
    shock_g:     NonNegativeFloat
    location:    Optional[str]  = Field(None, max_length=128)


class ShipmentAuditIn(_OmniBase):
    order_id:        str                  = Field(..., min_length=1, max_length=64)
    sensor_log:      list[SensorReading]  = Field(..., min_length=1)
    bom_expected:    list[str]            = Field(..., min_length=1)
    bom_scanned:     list[str]            = Field(..., min_length=1)
    temp_band_min:   float                = -20.0
    temp_band_max:   float                = 40.0
    max_shock_g:     PositiveFloat        = 6.0
    humidity_max:    float                = Field(85.0, ge=0, le=100)


class ShipmentAuditOut(_OmniBase):
    id:               int
    order_id:         str
    bom_compliance:   float
    temp_min:         float
    temp_max:         float
    shock_events:     NonNegativeInt
    humidity_avg:     float
    andon_triggered:  bool
    andon_reasons:    Optional[list[str]]
    status:           ShipmentStatus
    created_at:       datetime


class ProcessDeviationIn(_OmniBase):
    trace_id:           str         = Field(..., min_length=1, max_length=64)
    process_name:       str         = Field(..., min_length=1, max_length=64)
    expected_sequence:  list[str]   = Field(..., min_length=1, max_length=256)
    actual_sequence:    list[str]   = Field(..., min_length=1, max_length=256)
    co_occurrence:      Optional[dict[str, dict[str, int]]] = None


class ProcessDeviationOut(_OmniBase):
    id:                int
    trace_id:          str
    process_name:      str
    damerau_distance:  NonNegativeInt
    deviation_pct:     float
    deviation_steps:   Optional[list[str]]
    heuristic_dab:     Optional[dict[str, Any]]
    severity:          Severity
    created_at:        datetime


class PortfolioCandidate(_OmniBase):
    sku:               str               = Field(..., min_length=1, max_length=64)
    expected_return:   float
    sigma:             NonNegativeFloat
    avg_lead_days:     PositiveFloat
    capital_per_unit:  PositiveFloat


class PortfolioDecisionIn(_OmniBase):
    candidates:     list[PortfolioCandidate] = Field(..., min_length=2)
    risk_free_rate: float                    = Field(0.0, ge=-0.5, le=0.5)
    top_k:          PositiveInt              = 5
    method:         str                      = Field("SHARPE_ROT", pattern=r"^[A-Z_]+$")


class PortfolioDecisionOut(_OmniBase):
    id:                int
    snapshot_at:       datetime
    sku_universe:      list[str]
    rot_vector:        list[float]
    sharpe_rot_vector: list[float]
    risk_free_rate:    float
    selected_skus:     list[str]
    selected_weights:  list[NonNegativeFloat]
    expected_return:   float
    portfolio_sigma:   NonNegativeFloat
    method:            str


class HybridInferenceRequest(_OmniBase):
    request_kind:        str               = Field(..., min_length=1, max_length=32)
    prompt:              str               = Field(..., min_length=1, max_length=32000)
    require_local_first: bool              = True
    max_latency_ms:      PositiveInt       = 6000
    min_confidence:      float             = Field(0.55, ge=0, le=1)
    context_hints:       Optional[dict[str, Any]] = None


class HybridInferenceResponse(_OmniBase):
    id:                 int
    request_kind:       str
    routed_to:          HybridRoute
    prompt_tokens:      NonNegativeInt
    completion_tokens:  NonNegativeInt
    latency_ms:         NonNegativeInt
    cost_usd:           NonNegativeFloat
    confidence:         float
    fallback_triggered: bool
    response_text:      Optional[str] = None
    error_message:      Optional[str] = None
    created_at:         datetime


class AnomalyEventIn(_OmniBase):
    source_table: str       = Field(..., min_length=1, max_length=64)
    source_id:    PositiveInt
    severity:     Severity   = Severity.LOW
    description:  str        = Field(..., min_length=1, max_length=1024)


class AnomalyEventOut(_OmniBase):
    id:           int
    source_table: str
    source_id:    PositiveInt
    severity:     Severity
    description:  str
    resolved:     bool
    resolved_at:  Optional[datetime]
    created_at:   datetime


__all__ = [
    "RiskLevel", "Severity", "HybridRoute", "ShipmentStatus",
    "ADRAction", "IPDecision",
    "InventoryDecisionIn", "InventoryDecisionOut",
    "CarrierCandidate", "CarrierSelectionIn", "CarrierSelectionOut",
    "ForexPositionIn", "ForexPositionOut",
    "IPInfringementCheck", "IPInfringementOut",
    "ADRCaseRequest", "ADRCaseOut",
    "SensorReading", "ShipmentAuditIn", "ShipmentAuditOut",
    "ProcessDeviationIn", "ProcessDeviationOut",
    "PortfolioCandidate", "PortfolioDecisionIn", "PortfolioDecisionOut",
    "HybridInferenceRequest", "HybridInferenceResponse",
    "AnomalyEventIn", "AnomalyEventOut",
]
