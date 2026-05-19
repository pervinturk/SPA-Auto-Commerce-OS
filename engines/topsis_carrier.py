from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select

from core.database_async import AsyncSessionLocal, CarrierSelection
from core.schemas import (CarrierCandidate, CarrierSelectionIn,
                            CarrierSelectionOut)


CRITERIA_LABELS = ("cost", "eta_days", "damage_pct", "on_time", "sla_pen")
EPS = 1e-12


@dataclass
class TOPSISResult:
    candidates:        list[str]
    criteria_matrix:   list[list[float]]
    weights:           list[float]
    impact_signs:      list[int]
    normalized:        list[list[float]]
    weighted:          list[list[float]]
    ideal_best:        list[float]
    ideal_worst:       list[float]
    s_plus:            list[float]
    s_minus:           list[float]
    closeness_scores:  list[float]
    ranked_indices:    list[int]
    selected_carrier:  str
    selected_index:    int

    def to_dict(self) -> dict:
        return {
            "candidates":       list(self.candidates),
            "criteria_matrix":  [list(row) for row in self.criteria_matrix],
            "weights":          list(self.weights),
            "impact_signs":     list(self.impact_signs),
            "normalized":       [list(row) for row in self.normalized],
            "weighted":         [list(row) for row in self.weighted],
            "ideal_best":       list(self.ideal_best),
            "ideal_worst":      list(self.ideal_worst),
            "s_plus":           list(self.s_plus),
            "s_minus":          list(self.s_minus),
            "closeness_scores": list(self.closeness_scores),
            "ranked_indices":   list(self.ranked_indices),
            "selected_carrier": self.selected_carrier,
            "selected_index":   self.selected_index,
        }


def _validate_inputs(matrix: list[list[float]],
                       weights: list[float],
                       impacts: list[int]) -> tuple[int, int]:
    if not matrix:
        raise ValueError("criteria_matrix boş olamaz")
    n = len(matrix)
    m = len(matrix[0])
    if any(len(row) != m for row in matrix):
        raise ValueError("criteria_matrix tüm satırlar aynı uzunlukta olmalı")
    if len(weights) != m:
        raise ValueError(f"weights uzunluğu {m} olmalı")
    if len(impacts) != m:
        raise ValueError(f"impact_signs uzunluğu {m} olmalı")
    if any(s not in (-1, 1) for s in impacts):
        raise ValueError("impact_signs ±1 olmalı")
    if any(w <= 0 for w in weights):
        raise ValueError("tüm weights pozitif olmalı")
    return n, m


def _vector_normalize(matrix: list[list[float]],
                        n: int, m: int) -> list[list[float]]:
    col_norms = []
    for j in range(m):
        col_sq = sum(matrix[i][j] ** 2 for i in range(n))
        col_norms.append(math.sqrt(col_sq) if col_sq > 0 else EPS)
    return [[matrix[i][j] / col_norms[j] for j in range(m)]
            for i in range(n)]


def topsis(matrix: list[list[float]],
             weights: list[float],
             impact_signs: list[int],
             names: Sequence[str] = ()) -> TOPSISResult:
    n, m = _validate_inputs(matrix, weights, impact_signs)
    if not names:
        names = [f"alt_{i+1}" for i in range(n)]

    normalized = _vector_normalize(matrix, n, m)

    weighted = [[normalized[i][j] * weights[j] for j in range(m)]
                for i in range(n)]

    ideal_best: list[float] = []
    ideal_worst: list[float] = []
    for j in range(m):
        col = [weighted[i][j] for i in range(n)]
        if impact_signs[j] == 1:
            ideal_best.append(max(col))
            ideal_worst.append(min(col))
        else:
            ideal_best.append(min(col))
            ideal_worst.append(max(col))

    s_plus: list[float] = []
    s_minus: list[float] = []
    for i in range(n):
        sp = math.sqrt(sum((weighted[i][j] - ideal_best[j]) ** 2
                              for j in range(m)))
        sm = math.sqrt(sum((weighted[i][j] - ideal_worst[j]) ** 2
                              for j in range(m)))
        s_plus.append(sp)
        s_minus.append(sm)

    closeness: list[float] = []
    for i in range(n):
        denom = s_plus[i] + s_minus[i]
        closeness.append(s_minus[i] / denom if denom > 0 else 0.0)

    ranked = sorted(range(n), key=lambda i: -closeness[i])
    sel_idx = ranked[0]

    return TOPSISResult(
        candidates=list(names),
        criteria_matrix=[list(row) for row in matrix],
        weights=list(weights),
        impact_signs=list(impact_signs),
        normalized=normalized,
        weighted=weighted,
        ideal_best=ideal_best,
        ideal_worst=ideal_worst,
        s_plus=s_plus,
        s_minus=s_minus,
        closeness_scores=closeness,
        ranked_indices=ranked,
        selected_carrier=names[sel_idx],
        selected_index=sel_idx,
    )


def select_from_candidates(candidates: Sequence[CarrierCandidate],
                              weights: list[float],
                              impact_signs: list[int]) -> TOPSISResult:
    matrix = [[float(c.cost), float(c.eta_days), float(c.damage_pct),
                float(c.on_time), float(c.sla_pen)]
                for c in candidates]
    names = [c.name for c in candidates]
    return topsis(matrix, weights, impact_signs, names=names)


async def persist_selection(req: CarrierSelectionIn) -> CarrierSelectionOut:
    result = select_from_candidates(req.candidates, list(req.weights),
                                       list(req.impact_signs))
    async with AsyncSessionLocal() as session:
        row = CarrierSelection(
            order_id=req.order_id,
            criteria_matrix=result.criteria_matrix,
            weights=result.weights,
            impact_signs=result.impact_signs,
            candidates=result.candidates,
            ideal_best=result.ideal_best,
            ideal_worst=result.ideal_worst,
            closeness_scores=result.closeness_scores,
            selected_carrier=result.selected_carrier,
            selected_index=int(result.selected_index),
            method="TOPSIS",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return CarrierSelectionOut.model_validate(row)


async def latest_for_order(order_id: str) -> CarrierSelectionOut | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(CarrierSelection)
            .where(CarrierSelection.order_id == order_id)
            .order_by(CarrierSelection.created_at.desc())
            .limit(1))).scalar_one_or_none()
        if row is None:
            return None
        return CarrierSelectionOut.model_validate(row)


__all__ = [
    "TOPSISResult", "topsis", "select_from_candidates",
    "persist_selection", "latest_for_order",
    "CRITERIA_LABELS",
]
