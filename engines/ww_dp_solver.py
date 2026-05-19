from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from core.database_async import AsyncSessionLocal, InventoryDecision
from core.schemas import InventoryDecisionIn, InventoryDecisionOut


Z_TABLE = {
    0.50: 0.00, 0.60: 0.25, 0.70: 0.52, 0.75: 0.67,
    0.80: 0.84, 0.85: 1.04, 0.90: 1.28, 0.91: 1.34,
    0.92: 1.41, 0.93: 1.48, 0.94: 1.55, 0.95: 1.65,
    0.96: 1.75, 0.97: 1.88, 0.98: 2.05, 0.99: 2.33,
    0.995: 2.58, 0.999: 3.09, 0.9999: 3.72,
}

INF = float("inf")


def _z_score(service_level: float) -> float:
    keys = sorted(Z_TABLE.keys())
    if service_level <= keys[0]:
        return Z_TABLE[keys[0]]
    if service_level >= keys[-1]:
        return Z_TABLE[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= service_level <= hi:
            t = (service_level - lo) / (hi - lo)
            return Z_TABLE[lo] + t * (Z_TABLE[hi] - Z_TABLE[lo])
    return 1.65


def _demand_stats(demand: list[float]) -> tuple[float, float]:
    n = len(demand)
    if n == 0:
        return 0.0, 0.0
    mu = sum(demand) / n
    if n < 2:
        return mu, 0.0
    var = sum((d - mu) ** 2 for d in demand) / (n - 1)
    return mu, math.sqrt(var)


def _apply_safety_stock(demand: list[float],
                          service_level: float,
                          lead_time: float = 1.0) -> list[float]:
    if service_level <= 0.50 or service_level >= 1.0:
        return list(demand)
    _, sigma = _demand_stats(demand)
    if sigma <= 0:
        return list(demand)
    ss = _z_score(service_level) * sigma * math.sqrt(max(lead_time, 1.0))
    if ss <= 0:
        return list(demand)
    bucket = ss / max(1, len(demand))
    return [d + bucket for d in demand]


@dataclass
class LotSizingResult:
    method:        str
    horizon:       int
    demand_vector: list[float]
    lot_sizes:     list[float]
    order_periods: list[int]
    total_cost:    float
    setup_total:   float
    holding_total: float
    purchase_cost: float
    avg_lot_size:  float

    def to_dict(self) -> dict:
        return {
            "method":        self.method,
            "horizon":       self.horizon,
            "demand_vector": list(self.demand_vector),
            "lot_sizes":     list(self.lot_sizes),
            "order_periods": list(self.order_periods),
            "total_cost":    float(self.total_cost),
            "setup_total":   float(self.setup_total),
            "holding_total": float(self.holding_total),
            "purchase_cost": float(self.purchase_cost),
            "avg_lot_size":  float(self.avg_lot_size),
        }


def _finalize(method: str, demand: list[float],
                lot_sizes: list[float], order_periods: list[int],
                setup_cost: float, holding_cost: float,
                unit_cost: float) -> LotSizingResult:
    T = len(demand)
    setup_total = setup_cost * len(order_periods)
    holding_total = 0.0
    inventory = 0.0
    for t in range(T):
        if t in order_periods:
            inventory += lot_sizes[t]
        inventory -= demand[t]
        if inventory < 0:
            inventory = 0
        holding_total += holding_cost * inventory
    purchase_cost = unit_cost * sum(demand)
    total = setup_total + holding_total + purchase_cost
    placed = [q for q in lot_sizes if q > 0]
    avg = sum(placed) / len(placed) if placed else 0.0
    return LotSizingResult(
        method=method, horizon=T,
        demand_vector=list(demand), lot_sizes=list(lot_sizes),
        order_periods=list(order_periods), total_cost=total,
        setup_total=setup_total, holding_total=holding_total,
        purchase_cost=purchase_cost, avg_lot_size=avg)


def solve_wagner_whitin(demand: list[float],
                          setup_cost: float,
                          holding_cost: float,
                          unit_cost: float = 0.0) -> LotSizingResult:
    T = len(demand)
    if T == 0:
        return LotSizingResult("WAGNER_WHITIN", 0, [], [], [], 0.0, 0.0, 0.0, 0.0, 0.0)

    F = [0.0] * (T + 1)
    last_order = [0] * (T + 1)

    for t in range(1, T + 1):
        if demand[t - 1] == 0:
            F[t] = F[t - 1]
            last_order[t] = last_order[t - 1]
            for j in range(1, t + 1):
                if demand[j - 1] == 0:
                    continue
                holding = 0.0
                for k in range(j, t + 1):
                    holding += holding_cost * (k - j) * demand[k - 1]
                cand = F[j - 1] + setup_cost + holding
                if cand < F[t]:
                    F[t] = cand
                    last_order[t] = j
            continue
        best_cost = INF
        best_j = t
        for j in range(1, t + 1):
            if demand[j - 1] == 0:
                continue
            holding = 0.0
            for k in range(j, t + 1):
                holding += holding_cost * (k - j) * demand[k - 1]
            cand = F[j - 1] + setup_cost + holding
            if cand < best_cost:
                best_cost = cand
                best_j = j
        F[t] = best_cost
        last_order[t] = best_j

    order_periods: list[int] = []
    t = T
    while t > 0:
        j = last_order[t]
        if j == 0:
            break
        if not order_periods or order_periods[-1] != j - 1:
            order_periods.append(j - 1)
        t = j - 1
    order_periods.reverse()

    lot_sizes = [0.0] * T
    for i, op in enumerate(order_periods):
        nxt = order_periods[i + 1] if (i + 1) < len(order_periods) else T
        lot_sizes[op] = sum(demand[op:nxt])

    return _finalize("WAGNER_WHITIN", demand, lot_sizes, order_periods,
                       setup_cost, holding_cost, unit_cost)


def solve_silver_meal(demand: list[float],
                        setup_cost: float,
                        holding_cost: float,
                        unit_cost: float = 0.0) -> LotSizingResult:
    T = len(demand)
    if T == 0:
        return LotSizingResult("SILVER_MEAL", 0, [], [], [], 0.0, 0.0, 0.0, 0.0, 0.0)

    order_periods: list[int] = []
    lot_sizes = [0.0] * T
    j = 0
    while j < T:
        order_periods.append(j)
        prev_trc = INF
        cum_holding = 0.0
        best_t = j
        for t in range(j, T):
            if t > j:
                cum_holding += holding_cost * (t - j) * demand[t]
            trc = (setup_cost + cum_holding) / (t - j + 1)
            if trc <= prev_trc:
                prev_trc = trc
                best_t = t
            else:
                break
        lot_sizes[j] = sum(demand[j:best_t + 1])
        j = best_t + 1

    return _finalize("SILVER_MEAL", demand, lot_sizes, order_periods,
                       setup_cost, holding_cost, unit_cost)


def solve_lot_for_lot(demand: list[float],
                        setup_cost: float,
                        holding_cost: float,
                        unit_cost: float = 0.0) -> LotSizingResult:
    T = len(demand)
    order_periods = [t for t in range(T) if demand[t] > 0]
    lot_sizes = [d if d > 0 else 0.0 for d in demand]
    return _finalize("LOT_FOR_LOT", demand, lot_sizes, order_periods,
                       setup_cost, holding_cost, unit_cost)


def solve_eoq_baseline(demand: list[float],
                         setup_cost: float,
                         holding_cost: float,
                         unit_cost: float = 0.0) -> LotSizingResult:
    T = len(demand)
    total_demand = sum(demand)
    if total_demand <= 0 or holding_cost <= 0:
        return _finalize("EOQ", demand, [0.0] * T, [], setup_cost, holding_cost, unit_cost)
    annualized_h = holding_cost * T
    Q_star = math.sqrt((2.0 * total_demand * setup_cost) / annualized_h)
    lot_sizes = [0.0] * T
    order_periods: list[int] = []
    inventory = 0.0
    for t in range(T):
        if inventory < demand[t]:
            order_periods.append(t)
            qty = max(Q_star, demand[t] - inventory)
            lot_sizes[t] = qty
            inventory += qty
        inventory -= demand[t]
        if inventory < 0:
            inventory = 0
    return _finalize("EOQ", demand, lot_sizes, order_periods,
                       setup_cost, holding_cost, unit_cost)


def compare_methods(demand: list[float],
                      setup_cost: float,
                      holding_cost: float,
                      unit_cost: float = 0.0) -> dict[str, LotSizingResult]:
    return {
        "WAGNER_WHITIN": solve_wagner_whitin(demand, setup_cost, holding_cost, unit_cost),
        "SILVER_MEAL":   solve_silver_meal(demand, setup_cost, holding_cost, unit_cost),
        "EOQ":            solve_eoq_baseline(demand, setup_cost, holding_cost, unit_cost),
        "LOT_FOR_LOT":   solve_lot_for_lot(demand, setup_cost, holding_cost, unit_cost),
    }


def best_method(results: dict[str, LotSizingResult]) -> tuple[str, LotSizingResult]:
    items = list(results.items())
    items.sort(key=lambda kv: kv[1].total_cost)
    return items[0]


def lumpy_demand_score(demand: list[float]) -> float:
    n = len(demand)
    if n == 0:
        return 0.0
    mu, sigma = _demand_stats(demand)
    if mu <= 0:
        return 0.0
    cv = sigma / mu
    zeros = sum(1 for d in demand if d == 0)
    zero_ratio = zeros / n
    return float(min(1.0, 0.6 * cv + 0.4 * zero_ratio))


async def persist_decision(req: InventoryDecisionIn,
                              result: LotSizingResult) -> InventoryDecisionOut:
    async with AsyncSessionLocal() as session:
        row = InventoryDecision(
            sku=req.sku,
            horizon=result.horizon,
            demand_vector=list(result.demand_vector),
            setup_cost=float(req.setup_cost),
            holding_cost=float(req.holding_cost),
            unit_cost=float(req.unit_cost),
            lot_sizes=list(result.lot_sizes),
            total_cost=float(result.total_cost),
            order_periods=list(result.order_periods),
            avg_lot_size=float(result.avg_lot_size),
            service_level=float(req.service_level),
            method=result.method,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return InventoryDecisionOut.model_validate(row)


async def solve_and_persist(req: InventoryDecisionIn,
                              apply_safety_stock: bool = True,
                              lead_time: float = 1.0
                              ) -> InventoryDecisionOut:
    demand = list(req.demand_vector)
    if apply_safety_stock:
        demand = _apply_safety_stock(demand, req.service_level, lead_time)
    result = solve_wagner_whitin(
        demand, float(req.setup_cost), float(req.holding_cost),
        float(req.unit_cost))
    return await persist_decision(req, result)


async def latest_decision_for(sku: str) -> Optional[InventoryDecisionOut]:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(InventoryDecision)
            .where(InventoryDecision.sku == sku)
            .order_by(InventoryDecision.created_at.desc())
            .limit(1))).scalar_one_or_none()
        if row is None:
            return None
        return InventoryDecisionOut.model_validate(row)


__all__ = [
    "LotSizingResult",
    "solve_wagner_whitin", "solve_silver_meal", "solve_lot_for_lot",
    "solve_eoq_baseline", "compare_methods", "best_method",
    "lumpy_demand_score",
    "persist_decision", "solve_and_persist", "latest_decision_for",
    "Z_TABLE",
]
