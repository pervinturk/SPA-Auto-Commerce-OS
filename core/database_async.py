from __future__ import annotations
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy import (Integer, String, Float, Numeric, DateTime, Boolean,
                          Text, ForeignKey, JSON, Index, event)
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                       async_sessionmaker, create_async_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship)


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "omnicore.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

engine: AsyncEngine = create_async_engine(
    DB_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30.0},
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=-64000;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA temp_store=MEMORY;")
    cursor.execute("PRAGMA mmap_size=268435456;")
    cursor.close()


AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False,
    autoflush=False, autocommit=False,
)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.utcnow()


class InventoryDecision(Base):
    __tablename__ = "oc_inventory_decisions"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku:                Mapped[str]      = mapped_column(String(64), index=True, nullable=False)
    horizon:            Mapped[int]      = mapped_column(Integer, nullable=False)
    demand_vector:      Mapped[list]     = mapped_column(JSON, nullable=False)
    setup_cost:         Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False)
    holding_cost:       Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False)
    unit_cost:          Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False, default=0)
    lot_sizes:          Mapped[list]     = mapped_column(JSON, nullable=False)
    total_cost:         Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False)
    order_periods:      Mapped[list]     = mapped_column(JSON, nullable=False)
    avg_lot_size:       Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False, default=0)
    service_level:      Mapped[float]    = mapped_column(Float, nullable=False, default=0.95)
    method:             Mapped[str]      = mapped_column(String(32), nullable=False, default="WAGNER_WHITIN")
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class CarrierSelection(Base):
    __tablename__ = "oc_carrier_selections"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id:           Mapped[Optional[str]] = mapped_column(String(64), index=True)
    criteria_matrix:    Mapped[list]     = mapped_column(JSON, nullable=False)
    weights:            Mapped[list]     = mapped_column(JSON, nullable=False)
    impact_signs:       Mapped[list]     = mapped_column(JSON, nullable=False)
    candidates:         Mapped[list]     = mapped_column(JSON, nullable=False)
    ideal_best:         Mapped[list]     = mapped_column(JSON, nullable=False)
    ideal_worst:        Mapped[list]     = mapped_column(JSON, nullable=False)
    closeness_scores:   Mapped[list]     = mapped_column(JSON, nullable=False)
    selected_carrier:   Mapped[str]      = mapped_column(String(64), nullable=False)
    selected_index:     Mapped[int]      = mapped_column(Integer, nullable=False)
    method:             Mapped[str]      = mapped_column(String(32), nullable=False, default="TOPSIS")
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ForexPosition(Base):
    __tablename__ = "oc_forex_positions"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair:               Mapped[str]      = mapped_column(String(16), index=True, nullable=False)
    notional:           Mapped[float]    = mapped_column(Numeric(18, 4), nullable=False)
    horizon_days:       Mapped[int]      = mapped_column(Integer, nullable=False, default=10)
    confidence:         Mapped[float]    = mapped_column(Float, nullable=False, default=0.99)
    mu_daily:           Mapped[float]    = mapped_column(Float, nullable=False)
    sigma_daily:        Mapped[float]    = mapped_column(Float, nullable=False)
    z_score:            Mapped[float]    = mapped_column(Float, nullable=False)
    parametric_var:     Mapped[float]    = mapped_column(Numeric(18, 4), nullable=False)
    expected_shortfall: Mapped[float]    = mapped_column(Numeric(18, 4), nullable=False, default=0)
    hedge_recommended:  Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    hedge_ratio:        Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    method:             Mapped[str]      = mapped_column(String(32), nullable=False, default="PARAMETRIC_BROWNIAN")
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class IPInfringement(Base):
    __tablename__ = "oc_ip_infringements"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_sku:        Mapped[str]      = mapped_column(String(64), index=True, nullable=False)
    candidate_url:      Mapped[Optional[str]] = mapped_column(String(512))
    target_phash:       Mapped[str]      = mapped_column(String(32), nullable=False)
    candidate_phash:    Mapped[str]      = mapped_column(String(32), nullable=False)
    hamming_distance:   Mapped[int]      = mapped_column(Integer, nullable=False)
    similarity_pct:     Mapped[float]    = mapped_column(Float, nullable=False)
    trademark_tfidf:    Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    decision:           Mapped[str]      = mapped_column(String(32), nullable=False)
    risk_level:         Mapped[str]      = mapped_column(String(16), nullable=False, default="LOW")
    metadata_json:      Mapped[Optional[dict]] = mapped_column(JSON)
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ADRCase(Base):
    __tablename__ = "oc_adr_cases"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id:           Mapped[str]      = mapped_column(String(64), index=True, nullable=False)
    customer_id:        Mapped[Optional[str]] = mapped_column(String(64), index=True)
    dispute_type:       Mapped[str]      = mapped_column(String(32), nullable=False)
    claimed_amount:     Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False, default=0)
    evidence_score:     Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    cltv_score:         Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    repeat_risk:        Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    decision_matrix:    Mapped[dict]     = mapped_column(JSON, nullable=False)
    recommended_action: Mapped[str]      = mapped_column(String(32), nullable=False)
    expected_cost:      Mapped[float]    = mapped_column(Numeric(14, 4), nullable=False, default=0)
    settled:            Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    settled_at:         Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ShipmentAudit(Base):
    __tablename__ = "oc_shipment_audits"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id:           Mapped[str]      = mapped_column(String(64), index=True, nullable=False)
    sensor_log:         Mapped[list]     = mapped_column(JSON, nullable=False)
    bom_expected:       Mapped[list]     = mapped_column(JSON, nullable=False)
    bom_scanned:        Mapped[list]     = mapped_column(JSON, nullable=False)
    bom_compliance:     Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    temp_min:           Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    temp_max:           Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    shock_events:       Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    humidity_avg:       Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    andon_triggered:    Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    andon_reasons:      Mapped[Optional[list]] = mapped_column(JSON)
    status:             Mapped[str]      = mapped_column(String(16), nullable=False, default="PENDING")
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ProcessTrace(Base):
    __tablename__ = "oc_process_traces"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id:           Mapped[str]      = mapped_column(String(64), index=True, nullable=False)
    process_name:       Mapped[str]      = mapped_column(String(64), nullable=False)
    expected_sequence:  Mapped[list]     = mapped_column(JSON, nullable=False)
    actual_sequence:    Mapped[list]     = mapped_column(JSON, nullable=False)
    damerau_distance:   Mapped[int]      = mapped_column(Integer, nullable=False)
    deviation_pct:      Mapped[float]    = mapped_column(Float, nullable=False)
    deviation_steps:    Mapped[Optional[list]] = mapped_column(JSON)
    heuristic_dab:      Mapped[Optional[dict]] = mapped_column(JSON)
    severity:           Mapped[str]      = mapped_column(String(16), nullable=False, default="LOW")
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class PortfolioDecision(Base):
    __tablename__ = "oc_portfolio_decisions"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_at:        Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    sku_universe:       Mapped[list]     = mapped_column(JSON, nullable=False)
    rot_vector:         Mapped[list]     = mapped_column(JSON, nullable=False)
    sharpe_rot_vector:  Mapped[list]     = mapped_column(JSON, nullable=False)
    risk_free_rate:     Mapped[float]    = mapped_column(Float, nullable=False, default=0.0)
    selected_skus:      Mapped[list]     = mapped_column(JSON, nullable=False)
    selected_weights:   Mapped[list]     = mapped_column(JSON, nullable=False)
    expected_return:    Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    portfolio_sigma:    Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    method:             Mapped[str]      = mapped_column(String(32), nullable=False, default="SHARPE_ROT")


class HybridInferenceLog(Base):
    __tablename__ = "oc_hybrid_inference_log"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_kind:       Mapped[str]      = mapped_column(String(32), nullable=False)
    routed_to:          Mapped[str]      = mapped_column(String(16), nullable=False)
    prompt_tokens:      Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    completion_tokens:  Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    latency_ms:         Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    cost_usd:           Mapped[float]    = mapped_column(Numeric(10, 6), nullable=False, default=0)
    confidence:         Mapped[float]    = mapped_column(Float, nullable=False, default=0)
    fallback_triggered: Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    error_message:      Mapped[Optional[str]] = mapped_column(String(512))
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class AnomalyEvent(Base):
    __tablename__ = "oc_anomaly_events"

    id:                 Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_table:       Mapped[str]      = mapped_column(String(64), nullable=False)
    source_id:          Mapped[int]      = mapped_column(Integer, nullable=False)
    severity:           Mapped[str]      = mapped_column(String(16), nullable=False, default="LOW")
    description:        Mapped[str]      = mapped_column(Text, nullable=False)
    resolved:           Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    resolved_at:        Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at:         Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


Index("idx_oc_inv_sku_created",   InventoryDecision.sku, InventoryDecision.created_at.desc())
Index("idx_oc_carrier_order",     CarrierSelection.order_id)
Index("idx_oc_forex_pair_created", ForexPosition.pair, ForexPosition.created_at.desc())
Index("idx_oc_ip_listing",         IPInfringement.listing_sku, IPInfringement.created_at.desc())
Index("idx_oc_adr_order",          ADRCase.order_id, ADRCase.settled)
Index("idx_oc_shipment_order",     ShipmentAudit.order_id, ShipmentAudit.status)
Index("idx_oc_process_trace",      ProcessTrace.trace_id, ProcessTrace.severity)
Index("idx_oc_hybrid_kind",        HybridInferenceLog.request_kind, HybridInferenceLog.created_at.desc())
Index("idx_oc_anomaly_unresolved", AnomalyEvent.resolved, AnomalyEvent.severity)


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def shutdown() -> None:
    await engine.dispose()


__all__ = [
    "engine", "AsyncSessionLocal", "Base", "init_models", "drop_models",
    "get_session", "shutdown", "DB_PATH", "DB_URL",
    "InventoryDecision", "CarrierSelection", "ForexPosition",
    "IPInfringement", "ADRCase", "ShipmentAudit", "ProcessTrace",
    "PortfolioDecision", "HybridInferenceLog", "AnomalyEvent",
]
