from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, func

from core.database_async import (AsyncSessionLocal, ShipmentAudit,
                                    AnomalyEvent)
from core.schemas import (ShipmentAuditIn, ShipmentAuditOut, SensorReading,
                            ShipmentStatus, Severity)


COLD_CHAIN_BAND = (-20.0, 8.0)
AMBIENT_BAND = (-5.0, 35.0)
FROZEN_BAND = (-25.0, -15.0)

DEFAULT_SHOCK_EVENT_LIMIT = 3
DEFAULT_BOM_BLOCK_THRESHOLD = 0.50
CRITICAL_TEMP_DRIFT_PCT = 0.20


@dataclass
class SensorAggregate:
    n_readings:    int
    temp_min:      float
    temp_max:      float
    temp_mean:     float
    temp_range:    float
    humidity_min:  float
    humidity_max:  float
    humidity_mean: float
    shock_max:     float
    shock_mean:    float
    shock_events:  int

    def to_dict(self) -> dict:
        return {
            "n_readings":    self.n_readings,
            "temp_min":      self.temp_min,
            "temp_max":      self.temp_max,
            "temp_mean":     self.temp_mean,
            "temp_range":    self.temp_range,
            "humidity_min":  self.humidity_min,
            "humidity_max":  self.humidity_max,
            "humidity_mean": self.humidity_mean,
            "shock_max":     self.shock_max,
            "shock_mean":    self.shock_mean,
            "shock_events":  self.shock_events,
        }


def aggregate_sensors(readings: Sequence[SensorReading],
                        shock_threshold_g: float
                        ) -> SensorAggregate:
    if not readings:
        return SensorAggregate(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                 0.0, 0.0, 0)
    temps = [float(r.temperature) for r in readings]
    hums = [float(r.humidity) for r in readings]
    shocks = [float(r.shock_g) for r in readings]
    n = len(readings)
    shock_events = sum(1 for s in shocks if s > shock_threshold_g)
    return SensorAggregate(
        n_readings=n,
        temp_min=min(temps), temp_max=max(temps),
        temp_mean=sum(temps) / n,
        temp_range=max(temps) - min(temps),
        humidity_min=min(hums), humidity_max=max(hums),
        humidity_mean=sum(hums) / n,
        shock_max=max(shocks), shock_mean=sum(shocks) / n,
        shock_events=shock_events,
    )


def temperature_excursion(agg: SensorAggregate,
                            temp_min: float,
                            temp_max: float) -> Optional[str]:
    if agg.n_readings == 0:
        return "Sensör verisi yok"
    if agg.temp_min < temp_min:
        delta = temp_min - agg.temp_min
        return (f"Sıcaklık aşağı sapması: min={agg.temp_min:.1f}°C "
                f"< band={temp_min:.1f}°C  (Δ={delta:.1f}°C)")
    if agg.temp_max > temp_max:
        delta = agg.temp_max - temp_max
        return (f"Sıcaklık yukarı sapması: max={agg.temp_max:.1f}°C "
                f"> band={temp_max:.1f}°C  (Δ={delta:.1f}°C)")
    return None


def humidity_excursion(agg: SensorAggregate,
                         humidity_max: float) -> Optional[str]:
    if agg.n_readings == 0:
        return None
    if agg.humidity_max > humidity_max:
        delta = agg.humidity_max - humidity_max
        return (f"Nem aşımı: max=%{agg.humidity_max:.1f} "
                f"> band=%{humidity_max:.1f}  (Δ=%{delta:.1f})")
    return None


def shock_excursion(agg: SensorAggregate,
                      max_shock: float,
                      event_limit: int = DEFAULT_SHOCK_EVENT_LIMIT) -> Optional[str]:
    if agg.n_readings == 0:
        return None
    if agg.shock_max > max_shock:
        return (f"Şok eşiği aşıldı: peak={agg.shock_max:.2f}g "
                f"> max={max_shock:.2f}g")
    if agg.shock_events >= event_limit:
        return (f"Çoklu şok olayı: {agg.shock_events} olay "
                f"≥ limit {event_limit}")
    return None


@dataclass
class BOMCheckResult:
    compliance:    float
    matched:       list[str]
    missing:       list[str]
    extra:         list[str]
    expected_size: int
    scanned_size:  int

    def to_dict(self) -> dict:
        return {
            "compliance":    self.compliance,
            "matched":       list(self.matched),
            "missing":       list(self.missing),
            "extra":         list(self.extra),
            "expected_size": self.expected_size,
            "scanned_size":  self.scanned_size,
        }


def bom_compliance_check(expected: Sequence[str],
                           scanned: Sequence[str]) -> BOMCheckResult:
    exp_list = [str(x) for x in expected]
    scan_list = [str(x) for x in scanned]
    exp_set = set(exp_list)
    scan_set = set(scan_list)
    matched = exp_set & scan_set
    missing = exp_set - scan_set
    extra = scan_set - exp_set
    compliance = len(matched) / len(exp_set) if exp_set else 0.0
    return BOMCheckResult(
        compliance=float(compliance),
        matched=sorted(matched),
        missing=sorted(missing),
        extra=sorted(extra),
        expected_size=len(exp_set),
        scanned_size=len(scan_set),
    )


@dataclass
class AuditResult:
    sensor_agg:      SensorAggregate
    bom_check:       BOMCheckResult
    andon_triggered: bool
    andon_reasons:   list[str]
    status:          str
    severity:        str

    def to_dict(self) -> dict:
        return {
            "sensor_agg":      self.sensor_agg.to_dict(),
            "bom_check":       self.bom_check.to_dict(),
            "andon_triggered": self.andon_triggered,
            "andon_reasons":   list(self.andon_reasons),
            "status":          self.status,
            "severity":        self.severity,
        }


def evaluate_audit(agg: SensorAggregate,
                     bom: BOMCheckResult,
                     temp_band_min: float = AMBIENT_BAND[0],
                     temp_band_max: float = AMBIENT_BAND[1],
                     humidity_max: float = 85.0,
                     max_shock_g: float = 6.0,
                     shock_event_limit: int = DEFAULT_SHOCK_EVENT_LIMIT,
                     bom_block_threshold: float = DEFAULT_BOM_BLOCK_THRESHOLD
                     ) -> AuditResult:
    reasons: list[str] = []

    t_msg = temperature_excursion(agg, temp_band_min, temp_band_max)
    if t_msg:
        reasons.append(t_msg)

    h_msg = humidity_excursion(agg, humidity_max)
    if h_msg:
        reasons.append(h_msg)

    s_msg = shock_excursion(agg, max_shock_g, shock_event_limit)
    if s_msg:
        reasons.append(s_msg)

    if bom.expected_size > 0:
        if bom.missing:
            reasons.append(
                f"BOM eksik parça: {bom.missing} "
                f"(uyum=%{bom.compliance*100:.0f})")
        if bom.extra:
            reasons.append(f"BOM fazla parça: {bom.extra}")

    if not reasons and agg.n_readings == 0:
        reasons.append("Sensör verisi yok")

    if not reasons:
        return AuditResult(agg, bom, False, [],
                             ShipmentStatus.PASSED.value, Severity.LOW.value)

    is_blocked = False
    critical_flags = 0
    if t_msg:
        critical_flags += 1
    if s_msg and ("eşiği aşıldı" in s_msg or "Çoklu şok" in s_msg):
        critical_flags += 1
    if bom.expected_size > 0 and bom.compliance < bom_block_threshold:
        is_blocked = True
        critical_flags += 1

    if is_blocked or critical_flags >= 2:
        return AuditResult(agg, bom, True, reasons,
                             ShipmentStatus.BLOCKED.value, Severity.HIGH.value)

    sev = Severity.HIGH.value if critical_flags >= 1 else Severity.MEDIUM.value
    return AuditResult(agg, bom, True, reasons,
                         ShipmentStatus.ANDON.value, sev)


async def audit_and_persist(req: ShipmentAuditIn) -> ShipmentAuditOut:
    agg = aggregate_sensors(req.sensor_log, float(req.max_shock_g))
    bom = bom_compliance_check(req.bom_expected, req.bom_scanned)
    result = evaluate_audit(
        agg=agg, bom=bom,
        temp_band_min=float(req.temp_band_min),
        temp_band_max=float(req.temp_band_max),
        humidity_max=float(req.humidity_max),
        max_shock_g=float(req.max_shock_g),
    )

    serialized_log = [r.model_dump(mode="json") for r in req.sensor_log]

    async with AsyncSessionLocal() as session:
        row = ShipmentAudit(
            order_id=req.order_id,
            sensor_log=serialized_log,
            bom_expected=list(req.bom_expected),
            bom_scanned=list(req.bom_scanned),
            bom_compliance=float(bom.compliance),
            temp_min=float(agg.temp_min),
            temp_max=float(agg.temp_max),
            shock_events=int(agg.shock_events),
            humidity_avg=float(agg.humidity_mean),
            andon_triggered=bool(result.andon_triggered),
            andon_reasons=result.andon_reasons if result.andon_reasons else None,
            status=result.status,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        if result.andon_triggered:
            anomaly = AnomalyEvent(
                source_table="oc_shipment_audits",
                source_id=int(row.id),
                severity=result.severity,
                description=" | ".join(result.andon_reasons)[:1024],
            )
            session.add(anomaly)
            await session.commit()

        return ShipmentAuditOut.model_validate(row)


async def latest_for_order(order_id: str) -> Optional[ShipmentAuditOut]:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(ShipmentAudit)
            .where(ShipmentAudit.order_id == order_id)
            .order_by(ShipmentAudit.created_at.desc())
            .limit(1))).scalar_one_or_none()
        if row is None:
            return None
        return ShipmentAuditOut.model_validate(row)


async def andon_summary(hours: int = 24) -> dict:
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as session:
        total = (await session.execute(
            select(func.count(ShipmentAudit.id))
            .where(ShipmentAudit.created_at >= since))).scalar_one()
        andon = (await session.execute(
            select(func.count(ShipmentAudit.id))
            .where(ShipmentAudit.created_at >= since)
            .where(ShipmentAudit.andon_triggered.is_(True)))).scalar_one()
        blocked = (await session.execute(
            select(func.count(ShipmentAudit.id))
            .where(ShipmentAudit.created_at >= since)
            .where(ShipmentAudit.status == ShipmentStatus.BLOCKED.value))
            ).scalar_one()
        passed = (await session.execute(
            select(func.count(ShipmentAudit.id))
            .where(ShipmentAudit.created_at >= since)
            .where(ShipmentAudit.status == ShipmentStatus.PASSED.value))
            ).scalar_one()
    total = int(total or 0)
    return {
        "since_hours":   hours,
        "total":         total,
        "passed":        int(passed or 0),
        "andon":         int(andon or 0),
        "blocked":       int(blocked or 0),
        "pass_rate":     (int(passed or 0) / total) if total else 0.0,
        "andon_rate":    (int(andon or 0) / total) if total else 0.0,
        "blocked_rate":  (int(blocked or 0) / total) if total else 0.0,
    }


async def cold_chain_violations(limit: int = 20) -> list[ShipmentAuditOut]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ShipmentAudit)
            .where(ShipmentAudit.temp_max > COLD_CHAIN_BAND[1])
            .order_by(ShipmentAudit.created_at.desc())
            .limit(limit))).scalars().all()
    return [ShipmentAuditOut.model_validate(r) for r in rows]


__all__ = [
    "SensorAggregate", "BOMCheckResult", "AuditResult",
    "aggregate_sensors", "bom_compliance_check",
    "temperature_excursion", "humidity_excursion", "shock_excursion",
    "evaluate_audit",
    "audit_and_persist", "latest_for_order", "andon_summary",
    "cold_chain_violations",
    "COLD_CHAIN_BAND", "AMBIENT_BAND", "FROZEN_BAND",
]
