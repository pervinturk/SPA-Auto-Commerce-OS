from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

import numpy as np
from sqlalchemy import select, func

from core.database_async import AsyncSessionLocal, CarrierSelection
from core.schemas import (CarrierCandidate, CarrierSelectionIn,
                            CarrierSelectionOut)


CRITERIA_NAMES = ("cost", "eta_days", "damage_pct", "on_time", "sla_pen")
DEFAULT_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]
DEFAULT_IMPACT_SIGNS = [-1, -1, -1, +1, -1]


@dataclass
class TopsisResult:
    candidates:       list[str]
    criteria_matrix:  list[list[float]]
    normalized:       list[list[float]]
    weighted:         list[list[float]]
    weights:          list[float]
    impact_signs:     list[int]
    ideal_best:       list[float]
    ideal_worst:      list[float]
    distance_best:    list[float]
    distance_worst:   list[float]
    closeness_scores: list[float]
    ranking:          list[int]
    selected_index:   int
    selected_name:    str
    method:           str = "TOPSIS"

    def to_dict(self) -> dict:
        return {
            "candidates":       list(self.candidates),
            "criteria_matrix":  [list(r) for r in self.criteria_matrix],
            "normalized":       [list(r) for r in self.normalized],
            "weighted":         [list(r) for r in self.weighted],
            "weights":          list(self.weights),
            "impact_signs":     list(self.impact_signs),
            "ideal_best":       list(self.ideal_best),
            "ideal_worst":      list(self.ideal_worst),
            "distance_best":    list(self.distance_best),
            "distance_worst":   list(self.distance_worst),
            "closeness_scores": list(self.closeness_scores),
            "ranking":          list(self.ranking),
            "selected_index":   int(self.selected_index),
            "selected_name":    self.selected_name,
            "method":           self.method,
        }


def build_criteria_matrix(candidates: Sequence[CarrierCandidate]
                              ) -> list[list[float]]:
    matrix: list[list[float]] = []
    for c in candidates:
        matrix.append([
            float(c.cost),
            float(c.eta_days),
            float(c.damage_pct),
            float(c.on_time),
            float(c.sla_pen),
        ])
    return matrix


def vector_normalize(matrix: list[list[float]]) -> list[list[float]]:
    arr = np.asarray(matrix, dtype=np.float64)
    if arr.size == 0:
        return []
    col_norms = np.sqrt((arr ** 2).sum(axis=0))
    col_norms[col_norms == 0] = 1.0
    out = arr / col_norms
    return out.tolist()


def apply_weights(normalized: list[list[float]],
                    weights: Sequence[float]) -> list[list[float]]:
    arr = np.asarray(normalized, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    return (arr * w).tolist()


def ideal_extremes(weighted: list[list[float]],
                     impact_signs: Sequence[int]
                     ) -> tuple[list[float], list[float]]:
    arr = np.asarray(weighted, dtype=np.float64)
    signs = np.asarray(impact_signs, dtype=np.int64)
    best = np.zeros(arr.shape[1], dtype=np.float64)
    worst = np.zeros(arr.shape[1], dtype=np.float64)
    for j in range(arr.shape[1]):
        col = arr[:, j]
        if signs[j] >= 0:
            best[j] = float(col.max())
            worst[j] = float(col.min())
        else:
            best[j] = float(col.min())
            worst[j] = float(col.max())
    return best.tolist(), worst.tolist()


def euclidean_distance(weighted: list[list[float]],
                          reference: Sequence[float]) -> list[float]:
    arr = np.asarray(weighted, dtype=np.float64)
    ref = np.asarray(reference, dtype=np.float64)
    diffs = arr - ref
    return np.sqrt((diffs ** 2).sum(axis=1)).tolist()


def closeness_coefficient(d_best: Sequence[float],
                             d_worst: Sequence[float]) -> list[float]:
    out: list[float] = []
    for db, dw in zip(d_best, d_worst):
        denom = db + dw
        if denom == 0:
            out.append(0.0)
        else:
            out.append(float(dw / denom))
    return out


def topsis(candidates: Sequence[CarrierCandidate],
             weights: Sequence[float] = DEFAULT_WEIGHTS,
             impact_signs: Sequence[int] = DEFAULT_IMPACT_SIGNS
             ) -> TopsisResult:
    if not candidates:
        return TopsisResult(
            candidates=[], criteria_matrix=[], normalized=[],
            weighted=[], weights=list(weights),
            impact_signs=list(impact_signs),
            ideal_best=[], ideal_worst=[],
            distance_best=[], distance_worst=[],
            closeness_scores=[], ranking=[],
            selected_index=-1, selected_name="")

    names = [c.name for c in candidates]
    X = build_criteria_matrix(candidates)
    R = vector_normalize(X)
    V = apply_weights(R, weights)
    a_best, a_worst = ideal_extremes(V, impact_signs)
    s_best = euclidean_distance(V, a_best)
    s_worst = euclidean_distance(V, a_worst)
    C = closeness_coefficient(s_best, s_worst)
    ranking = sorted(range(len(C)), key=lambda i: -C[i])
    selected_idx = ranking[0]

    return TopsisResult(
        candidates=names, criteria_matrix=X, normalized=R, weighted=V,
        weights=list(weights), impact_signs=list(impact_signs),
        ideal_best=a_best, ideal_worst=a_worst,
        distance_best=s_best, distance_worst=s_worst,
        closeness_scores=C, ranking=ranking,
        selected_index=int(selected_idx),
        selected_name=names[selected_idx])


async def select_carrier(req: CarrierSelectionIn) -> CarrierSelectionOut:
    result = topsis(
        candidates=list(req.candidates),
        weights=list(req.weights),
        impact_signs=list(req.impact_signs))

    async with AsyncSessionLocal() as session:
        row = CarrierSelection(
            order_id=req.order_id,
            criteria_matrix=result.criteria_matrix,
            weights=list(result.weights),
            impact_signs=list(result.impact_signs),
            candidates=result.candidates,
            ideal_best=result.ideal_best,
            ideal_worst=result.ideal_worst,
            closeness_scores=result.closeness_scores,
            selected_carrier=result.selected_name,
            selected_index=int(result.selected_index),
            method=result.method,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return CarrierSelectionOut.model_validate(row)


async def latest_for_order(order_id: str) -> Optional[CarrierSelectionOut]:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(CarrierSelection)
            .where(CarrierSelection.order_id == order_id)
            .order_by(CarrierSelection.created_at.desc())
            .limit(1))).scalar_one_or_none()
        if row is None:
            return None
        return CarrierSelectionOut.model_validate(row)


async def carrier_win_rate(hours: int = 168) -> dict:
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(CarrierSelection.selected_carrier,
                    func.count(CarrierSelection.id))
            .where(CarrierSelection.created_at >= since)
            .group_by(CarrierSelection.selected_carrier))).all()
        total = (await session.execute(
            select(func.count(CarrierSelection.id))
            .where(CarrierSelection.created_at >= since))).scalar_one()
    total_i = int(total or 0)
    by_carrier: dict[str, dict] = {}
    for carrier, cnt in rows:
        c = int(cnt or 0)
        by_carrier[str(carrier)] = {
            "wins":     c,
            "win_rate": (c / total_i) if total_i else 0.0,
        }
    return {
        "since_hours": hours,
        "total":       total_i,
        "by_carrier":  by_carrier,
    }


def rank_carriers(candidates: Sequence[CarrierCandidate],
                    weights: Sequence[float] = DEFAULT_WEIGHTS,
                    impact_signs: Sequence[int] = DEFAULT_IMPACT_SIGNS
                    ) -> list[tuple[str, float]]:
    result = topsis(candidates, weights, impact_signs)
    return [(result.candidates[i], result.closeness_scores[i])
            for i in result.ranking]


def what_if_weights(candidates: Sequence[CarrierCandidate],
                      weight_scenarios: dict[str, Sequence[float]],
                      impact_signs: Sequence[int] = DEFAULT_IMPACT_SIGNS
                      ) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for label, w in weight_scenarios.items():
        r = topsis(candidates, w, impact_signs)
        out[label] = {
            "selected":         r.selected_name,
            "closeness_scores": dict(zip(r.candidates, r.closeness_scores)),
            "ranking":          [r.candidates[i] for i in r.ranking],
            "weights":          list(w),
        }
    return out


__all__ = [
    "TopsisResult",
    "build_criteria_matrix", "vector_normalize", "apply_weights",
    "ideal_extremes", "euclidean_distance", "closeness_coefficient",
    "topsis", "rank_carriers", "what_if_weights",
    "select_carrier", "latest_for_order", "carrier_win_rate",
    "CRITERIA_NAMES", "DEFAULT_WEIGHTS", "DEFAULT_IMPACT_SIGNS",
]
