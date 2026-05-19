from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, func

from core.database_async import AsyncSessionLocal, ProcessTrace, AnomalyEvent
from core.schemas import (ProcessDeviationIn, ProcessDeviationOut, Severity)


SEVERITY_LOW_PCT    = 0.10
SEVERITY_MED_PCT    = 0.25
SEVERITY_HIGH_PCT   = 0.50
HEURISTIC_DAB_THR   = 0.80
HEURISTIC_LOOP_THR  = 0.60


def damerau_levenshtein(a: Sequence, b: Sequence) -> int:
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
        ai = a[i - 1]
        for j in range(1, lb + 1):
            bj = b[j - 1]
            cost = 0 if ai == bj else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + cost,
            )
            if (i > 1 and j > 1
                    and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)
    return int(d[la][lb])


def alignment_steps(expected: Sequence[str],
                      actual: Sequence[str]) -> list[str]:
    la, lb = len(expected), len(actual)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    op = [[""] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
        op[i][0] = "DEL"
    for j in range(lb + 1):
        d[0][j] = j
        op[0][j] = "INS"
    op[0][0] = ""
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if expected[i - 1] == actual[j - 1] else 1
            choices = [
                (d[i - 1][j - 1] + cost,
                 "MATCH" if cost == 0 else f"SUB({expected[i-1]}>>{actual[j-1]})"),
                (d[i - 1][j] + 1, f"DEL({expected[i-1]})"),
                (d[i][j - 1] + 1, f"INS({actual[j-1]})"),
            ]
            best_cost, best_op = min(choices, key=lambda x: x[0])
            transposed = False
            if (i > 1 and j > 1
                    and expected[i - 1] == actual[j - 2]
                    and expected[i - 2] == actual[j - 1]):
                trans_cost = d[i - 2][j - 2] + cost
                if trans_cost <= best_cost:
                    best_cost = trans_cost
                    best_op = f"SWAP({expected[i-2]}<>{expected[i-1]})"
                    transposed = True
            d[i][j] = best_cost
            op[i][j] = best_op

    steps: list[str] = []
    i, j = la, lb
    while i > 0 or j > 0:
        cur_op = op[i][j]
        if not cur_op:
            break
        if cur_op == "MATCH":
            i, j = i - 1, j - 1
            continue
        if cur_op.startswith("SUB"):
            steps.append(cur_op)
            i, j = i - 1, j - 1
        elif cur_op.startswith("DEL"):
            steps.append(cur_op)
            i -= 1
        elif cur_op.startswith("INS"):
            steps.append(cur_op)
            j -= 1
        elif cur_op.startswith("SWAP"):
            steps.append(cur_op)
            i, j = i - 2, j - 2
        else:
            break
    steps.reverse()
    return steps


@dataclass
class HeuristicEdge:
    a:        str
    b:        str
    ab:       int
    ba:       int
    dependency: float
    is_loop:  bool
    edge_type: str

    def to_dict(self) -> dict:
        return {
            "a":          self.a,
            "b":          self.b,
            "ab":         self.ab,
            "ba":         self.ba,
            "dependency": self.dependency,
            "is_loop":    self.is_loop,
            "edge_type":  self.edge_type,
        }


def _direct_follows(traces: Sequence[Sequence[str]]) -> dict:
    counts: dict[tuple, int] = defaultdict(int)
    for tr in traces:
        for i in range(len(tr) - 1):
            counts[(tr[i], tr[i + 1])] += 1
    return dict(counts)


def heuristic_miner(traces: Sequence[Sequence[str]],
                      dep_threshold: float = HEURISTIC_DAB_THR,
                      loop_threshold: float = HEURISTIC_LOOP_THR
                      ) -> dict:
    df = _direct_follows(traces)
    activities = set()
    for tr in traces:
        for a in tr:
            activities.add(a)
    edges: list[HeuristicEdge] = []
    seen_pairs: set[tuple] = set()
    for (a, b), ab in df.items():
        if (a, b) in seen_pairs or (b, a) in seen_pairs:
            continue
        seen_pairs.add((a, b))
        ba = df.get((b, a), 0)
        if a == b:
            dep = ab / (ab + 1.0)
            edges.append(HeuristicEdge(a=a, b=b, ab=ab, ba=0,
                                          dependency=float(dep),
                                          is_loop=dep >= loop_threshold,
                                          edge_type="LOOP_1"))
            continue
        dep = (ab - ba) / (ab + ba + 1.0)
        edge_type = "SEQUENCE" if dep >= dep_threshold else (
                       "REVERSE" if dep <= -dep_threshold else "WEAK")
        edges.append(HeuristicEdge(
            a=a, b=b, ab=ab, ba=ba, dependency=float(dep),
            is_loop=False, edge_type=edge_type))

    return {
        "activities": sorted(activities),
        "direct_follows": {f"{a}->{b}": c for (a, b), c in df.items()},
        "edges": [e.to_dict() for e in edges],
        "dep_threshold": dep_threshold,
        "loop_threshold": loop_threshold,
    }


def dependency_coefficient(a: str, b: str,
                              traces: Sequence[Sequence[str]]) -> float:
    df = _direct_follows(traces)
    ab = df.get((a, b), 0)
    ba = df.get((b, a), 0)
    if a == b:
        if ab == 0:
            return 0.0
        return ab / (ab + 1.0)
    if ab == 0 and ba == 0:
        return 0.0
    return (ab - ba) / (ab + ba + 1.0)


@dataclass
class DeviationResult:
    damerau_distance: int
    deviation_pct:    float
    deviation_steps:  list[str]
    severity:         str
    heuristic_dab:    Optional[dict]

    def to_dict(self) -> dict:
        return {
            "damerau_distance": self.damerau_distance,
            "deviation_pct":    self.deviation_pct,
            "deviation_steps":  list(self.deviation_steps),
            "severity":         self.severity,
            "heuristic_dab":    self.heuristic_dab,
        }


def _severity_for(deviation_pct: float) -> str:
    if deviation_pct <= SEVERITY_LOW_PCT:
        return Severity.LOW.value
    if deviation_pct <= SEVERITY_MED_PCT:
        return Severity.MEDIUM.value
    return Severity.HIGH.value


def analyze_deviation(expected: Sequence[str],
                        actual: Sequence[str],
                        co_occurrence: Optional[dict] = None
                        ) -> DeviationResult:
    d = damerau_levenshtein(expected, actual)
    n = max(len(expected), len(actual)) or 1
    pct = d / n
    steps = alignment_steps(expected, actual)

    heuristic = None
    if co_occurrence:
        edges = []
        for a, sub in co_occurrence.items():
            for b, cnt in sub.items():
                if a == b:
                    continue
                ba = co_occurrence.get(b, {}).get(a, 0)
                dep = (cnt - ba) / (cnt + ba + 1.0)
                edges.append({
                    "a": a, "b": b, "ab": int(cnt), "ba": int(ba),
                    "dependency": float(dep),
                    "edge_type": ("SEQUENCE" if dep >= HEURISTIC_DAB_THR else
                                    ("REVERSE" if dep <= -HEURISTIC_DAB_THR else "WEAK")),
                })
        heuristic = {"edges": edges}

    return DeviationResult(
        damerau_distance=d,
        deviation_pct=float(pct),
        deviation_steps=steps,
        severity=_severity_for(pct),
        heuristic_dab=heuristic,
    )


async def persist_deviation(req: ProcessDeviationIn) -> ProcessDeviationOut:
    result = analyze_deviation(
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
            deviation_steps=result.deviation_steps if result.deviation_steps else None,
            heuristic_dab=result.heuristic_dab,
            severity=result.severity,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        if result.severity in (Severity.MEDIUM.value, Severity.HIGH.value):
            anomaly = AnomalyEvent(
                source_table="oc_process_traces",
                source_id=int(row.id),
                severity=result.severity,
                description=(f"{req.process_name} sapması: "
                              f"d={result.damerau_distance} "
                              f"(%{result.deviation_pct*100:.1f}) "
                              f"steps={result.deviation_steps[:5]}")[:1024],
            )
            session.add(anomaly)
            await session.commit()

        return ProcessDeviationOut.model_validate(row)


async def deviation_summary(hours: int = 24) -> dict:
    since = datetime.utcnow() - timedelta(hours=hours)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ProcessTrace.severity, func.count(ProcessTrace.id),
                    func.avg(ProcessTrace.deviation_pct))
            .where(ProcessTrace.created_at >= since)
            .group_by(ProcessTrace.severity))).all()
        total = (await session.execute(
            select(func.count(ProcessTrace.id))
            .where(ProcessTrace.created_at >= since))).scalar_one()
    by_severity = {}
    for sev, cnt, avg_pct in rows:
        by_severity[str(sev)] = {
            "count": int(cnt or 0),
            "avg_deviation_pct": float(avg_pct or 0.0),
        }
    return {
        "since_hours": hours,
        "total":       int(total or 0),
        "by_severity": by_severity,
    }


async def latest_for_trace(trace_id: str,
                               limit: int = 10) -> list[ProcessDeviationOut]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ProcessTrace)
            .where(ProcessTrace.trace_id == trace_id)
            .order_by(ProcessTrace.created_at.desc())
            .limit(limit))).scalars().all()
    return [ProcessDeviationOut.model_validate(r) for r in rows]


__all__ = [
    "HeuristicEdge", "DeviationResult",
    "damerau_levenshtein", "alignment_steps",
    "heuristic_miner", "dependency_coefficient",
    "analyze_deviation",
    "persist_deviation", "deviation_summary", "latest_for_trace",
]
