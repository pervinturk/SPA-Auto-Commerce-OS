from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import select

from core.database_async import AsyncSessionLocal, ProcessTrace
from core.schemas import (ProcessDeviationIn, ProcessDeviationOut, Severity)


SEVERITY_LOW_MAX = 0.20
SEVERITY_MED_MAX = 0.50


def damerau_levenshtein_seq(a: Sequence, b: Sequence) -> int:
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + cost,
            )
            if (i > 1 and j > 1
                    and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)
    return d[la][lb]


def deviation_pct(expected: Sequence, actual: Sequence,
                    distance: int) -> float:
    max_len = max(len(expected), len(actual))
    if max_len == 0:
        return 0.0
    return min(1.0, max(0.0, distance / max_len))


def severity_from_pct(pct: float) -> str:
    if pct <= SEVERITY_LOW_MAX:
        return Severity.LOW.value
    if pct <= SEVERITY_MED_MAX:
        return Severity.MEDIUM.value
    return Severity.HIGH.value


def diff_steps(expected: Sequence[str],
                 actual: Sequence[str]) -> dict:
    exp_set = set(expected)
    actual_set = set(actual)
    missing = [s for s in expected if s not in actual_set]
    unexpected = [s for s in actual if s not in exp_set]
    misordered: list[tuple[int, str, str]] = []
    for i in range(min(len(expected), len(actual))):
        if expected[i] != actual[i] and actual[i] in exp_set and expected[i] in actual_set:
            misordered.append((i, expected[i], actual[i]))
    return {
        "missing":    missing,
        "unexpected": unexpected,
        "misordered": [{"position": p, "expected": e, "actual": a}
                         for p, e, a in misordered],
    }


def heuristic_miner_dab_from_traces(traces: Sequence[Sequence[str]]) -> dict[str, dict[str, float]]:
    succ: dict[tuple[str, str], int] = {}
    activities: set[str] = set()
    for trace in traces:
        for i in range(len(trace) - 1):
            a = trace[i]
            b = trace[i + 1]
            succ[(a, b)] = succ.get((a, b), 0) + 1
            activities.add(a)
            activities.add(b)
        if trace:
            activities.add(trace[-1])
    return _build_dab(activities, succ)


def heuristic_miner_dab_from_cooccurrence(co_occurrence: dict[str, dict[str, int]]
                                              ) -> dict[str, dict[str, float]]:
    activities: set[str] = set(co_occurrence.keys())
    succ: dict[tuple[str, str], int] = {}
    for a, succ_map in co_occurrence.items():
        if not isinstance(succ_map, dict):
            continue
        for b, count in succ_map.items():
            activities.add(b)
            succ[(a, b)] = int(count)
    return _build_dab(activities, succ)


def _build_dab(activities: set[str],
                succ: dict[tuple[str, str], int]) -> dict[str, dict[str, float]]:
    dab: dict[str, dict[str, float]] = {}
    for a in sorted(activities):
        dab[a] = {}
        for b in sorted(activities):
            ab = succ.get((a, b), 0)
            if a == b:
                dab[a][b] = (ab / (ab + 1.0)) if ab > 0 else 0.0
            else:
                ba = succ.get((b, a), 0)
                if ab == 0 and ba == 0:
                    dab[a][b] = 0.0
                else:
                    dab[a][b] = (ab - ba) / (ab + ba + 1.0)
    return dab


def dependent_pairs(dab: dict[str, dict[str, float]],
                       threshold: float = 0.50) -> list[tuple[str, str, float]]:
    pairs = []
    for a, row in dab.items():
        for b, val in row.items():
            if a == b:
                continue
            if val >= threshold:
                pairs.append((a, b, float(val)))
    pairs.sort(key=lambda t: -t[2])
    return pairs


@dataclass
class TraceAnalysis:
    damerau_distance: int
    deviation_pct:    float
    deviation_steps:  Optional[list[str]]
    diff_detail:      dict
    heuristic_dab:    Optional[dict]
    dependent_pairs:  Optional[list[tuple[str, str, float]]]
    severity:         str

    def to_dict(self) -> dict:
        return {
            "damerau_distance": self.damerau_distance,
            "deviation_pct":    self.deviation_pct,
            "deviation_steps":  self.deviation_steps,
            "diff_detail":      self.diff_detail,
            "heuristic_dab":    self.heuristic_dab,
            "dependent_pairs":  self.dependent_pairs,
            "severity":         self.severity,
        }


def analyze_trace(expected: Sequence[str],
                    actual: Sequence[str],
                    co_occurrence: Optional[dict[str, dict[str, int]]] = None
                    ) -> TraceAnalysis:
    distance = damerau_levenshtein_seq(expected, actual)
    pct = deviation_pct(expected, actual, distance)
    diff = diff_steps(expected, actual)

    flat_steps: list[str] = []
    for m in diff["missing"]:
        flat_steps.append(f"MISSING:{m}")
    for u in diff["unexpected"]:
        flat_steps.append(f"UNEXPECTED:{u}")
    for mo in diff["misordered"]:
        flat_steps.append(f"MISORDERED@{mo['position']}:exp={mo['expected']}->act={mo['actual']}")

    dab: Optional[dict] = None
    dep_pairs: Optional[list[tuple[str, str, float]]] = None
    if co_occurrence:
        dab = heuristic_miner_dab_from_cooccurrence(co_occurrence)
        dep_pairs = dependent_pairs(dab)

    return TraceAnalysis(
        damerau_distance=int(distance),
        deviation_pct=float(pct),
        deviation_steps=flat_steps if flat_steps else None,
        diff_detail=diff,
        heuristic_dab=dab,
        dependent_pairs=dep_pairs,
        severity=severity_from_pct(pct),
    )


async def persist_trace(req: ProcessDeviationIn) -> ProcessDeviationOut:
    result = analyze_trace(
        expected=list(req.expected_sequence),
        actual=list(req.actual_sequence),
        co_occurrence=req.co_occurrence,
    )
    async with AsyncSessionLocal() as session:
        row = ProcessTrace(
            trace_id=req.trace_id,
            process_name=req.process_name,
            expected_sequence=list(req.expected_sequence),
            actual_sequence=list(req.actual_sequence),
            damerau_distance=result.damerau_distance,
            deviation_pct=result.deviation_pct,
            deviation_steps=result.deviation_steps,
            heuristic_dab=result.heuristic_dab,
            severity=result.severity,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return ProcessDeviationOut.model_validate(row)


async def deviations_by_process(process_name: str,
                                   limit: int = 20) -> list[ProcessDeviationOut]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ProcessTrace)
            .where(ProcessTrace.process_name == process_name)
            .order_by(ProcessTrace.created_at.desc())
            .limit(limit))).scalars().all()
    return [ProcessDeviationOut.model_validate(r) for r in rows]


__all__ = [
    "TraceAnalysis",
    "damerau_levenshtein_seq", "deviation_pct", "severity_from_pct",
    "diff_steps",
    "heuristic_miner_dab_from_traces",
    "heuristic_miner_dab_from_cooccurrence",
    "dependent_pairs", "analyze_trace",
    "persist_trace", "deviations_by_process",
]
