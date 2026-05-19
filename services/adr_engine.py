from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func

from core.database_async import AsyncSessionLocal, ADRCase
from core.schemas import ADRCaseRequest, ADRCaseOut, ADRAction


REPLACE_SHIPPING_COST = 30.0
ESCALATE_LEGAL_COST = 200.0
GOODWILL_VOUCHER_COST = 50.0
PLATFORM_PENALTY_MULTIPLIER = 0.50
CLTV_LOSS_BASE_MULTIPLIER = 1.20

LEGAL_KEYWORDS = ("COUNTERFEIT", "TRADEMARK", "LEGAL", "FRAUD",
                    "CHARGEBACK", "INTELLECTUAL")
SOFT_KEYWORDS = ("INQUIRY", "QUESTION", "INFORMATION", "FEEDBACK")


@dataclass
class ActionEvaluation:
    action:        str
    direct_cost:   float
    cltv_impact:   float
    penalty_risk:  float
    deters_repeat: float
    expected_cost: float

    def to_dict(self) -> dict:
        return {
            "action":        self.action,
            "direct_cost":   float(self.direct_cost),
            "cltv_impact":   float(self.cltv_impact),
            "penalty_risk":  float(self.penalty_risk),
            "deters_repeat": float(self.deters_repeat),
            "expected_cost": float(self.expected_cost),
        }


def _refund(req: ADRCaseRequest) -> ActionEvaluation:
    direct = float(req.claimed_amount)
    cltv_impact = 0.0
    penalty = 0.0
    deters_repeat = -direct * (1.0 - req.evidence_score) * 0.10
    total = direct + cltv_impact + penalty - max(0.0, deters_repeat)
    return ActionEvaluation("REFUND", direct, cltv_impact, penalty,
                              deters_repeat, total)


def _replace(req: ADRCaseRequest) -> ActionEvaluation:
    direct = float(req.product_cost) + REPLACE_SHIPPING_COST
    cltv_impact = 0.0
    penalty = float(req.claimed_amount) * 0.05 * (1.0 - req.evidence_score)
    deters_repeat = 0.0
    total = direct + cltv_impact + penalty
    return ActionEvaluation("REPLACE", direct, cltv_impact, penalty,
                              deters_repeat, total)


def _partial(req: ADRCaseRequest) -> ActionEvaluation:
    direct = float(req.claimed_amount) * 0.50
    cltv_impact = float(req.claimed_amount) * 0.30 * (1.0 - req.cltv_score)
    penalty = float(req.claimed_amount) * 0.08 * (1.0 - req.evidence_score)
    deters_repeat = -float(req.claimed_amount) * 0.05 * req.repeat_risk
    total = direct + cltv_impact + penalty - max(0.0, deters_repeat)
    return ActionEvaluation("PARTIAL", direct, cltv_impact, penalty,
                              deters_repeat, total)


def _reject(req: ADRCaseRequest) -> ActionEvaluation:
    direct = 0.0
    cltv_impact = float(req.claimed_amount) * CLTV_LOSS_BASE_MULTIPLIER * req.cltv_score
    penalty = (float(req.claimed_amount)
                * PLATFORM_PENALTY_MULTIPLIER * req.evidence_score)
    deters_repeat = float(req.claimed_amount) * 0.15 * req.repeat_risk
    total = direct + cltv_impact + penalty - deters_repeat
    return ActionEvaluation("REJECT", direct, cltv_impact, penalty,
                              deters_repeat, total)


def _escalate(req: ADRCaseRequest) -> ActionEvaluation:
    direct = ESCALATE_LEGAL_COST
    cltv_impact = float(req.claimed_amount) * 0.20 * req.cltv_score
    penalty = 0.0
    deters_repeat = 0.0
    total = direct + cltv_impact + penalty
    return ActionEvaluation("ESCALATE", direct, cltv_impact, penalty,
                              deters_repeat, total)


def _goodwill(req: ADRCaseRequest) -> ActionEvaluation:
    direct = GOODWILL_VOUCHER_COST
    cltv_impact = 0.0
    penalty = float(req.claimed_amount) * 0.10 * (1.0 - req.evidence_score)
    deters_repeat = 0.0
    total = direct + cltv_impact + penalty
    return ActionEvaluation("GOODWILL", direct, cltv_impact, penalty,
                              deters_repeat, total)


def evaluate_all_actions(req: ADRCaseRequest) -> dict[str, ActionEvaluation]:
    return {
        "REFUND":   _refund(req),
        "REPLACE":  _replace(req),
        "PARTIAL":  _partial(req),
        "REJECT":   _reject(req),
        "ESCALATE": _escalate(req),
        "GOODWILL": _goodwill(req),
    }


def _is_legal_dispute(dispute_type: str) -> bool:
    dt = (dispute_type or "").upper()
    return any(k in dt for k in LEGAL_KEYWORDS)


def _is_soft_dispute(dispute_type: str) -> bool:
    dt = (dispute_type or "").upper()
    return any(k in dt for k in SOFT_KEYWORDS)


@dataclass
class ADRDecision:
    recommended_action: str
    expected_cost:      float
    rationale:          str
    decision_matrix:    dict[str, dict]
    rules_applied:      list[str]

    def to_dict(self) -> dict:
        return {
            "recommended_action": self.recommended_action,
            "expected_cost":      float(self.expected_cost),
            "rationale":          self.rationale,
            "decision_matrix":    self.decision_matrix,
            "rules_applied":      list(self.rules_applied),
        }


def recommend(req: ADRCaseRequest) -> ADRDecision:
    actions = evaluate_all_actions(req)
    matrix = {k: v.to_dict() for k, v in actions.items()}
    rules: list[str] = []

    if _is_legal_dispute(req.dispute_type):
        rules.append("RULE_LEGAL_ESCALATE")
        chosen = "ESCALATE"
        rationale = (f"Hukuki/IP içerikli uyuşmazlık ({req.dispute_type}) — "
                       f"otomatik kademe yükseltme.")
    elif req.claimed_amount <= 0:
        rules.append("RULE_SOFT_CLAIM_GOODWILL")
        chosen = "GOODWILL"
        rationale = "Talep tutarı yok; iyi niyet jesti ile kapatma."
    elif _is_soft_dispute(req.dispute_type):
        rules.append("RULE_SOFT_INQUIRY_GOODWILL")
        chosen = "GOODWILL"
        rationale = "Soft sorgu/geri bildirim — iyi niyet kuponu yeterli."
    elif req.repeat_risk >= 0.75:
        rules.append("RULE_ANTI_FRAUD_REJECT")
        chosen = "REJECT"
        rationale = (f"Yüksek tekrar riski (%{req.repeat_risk*100:.0f}) — "
                       f"sistematik suistimal şüphesi.")
    elif req.evidence_score >= 0.80:
        if req.cltv_score >= 0.50:
            rules.append("RULE_STRONG_CASE_LOYAL_CUSTOMER_REFUND")
            chosen = "REFUND"
            rationale = (f"Güçlü kanıt (%{req.evidence_score*100:.0f}) + sadık "
                          f"müşteri (CLTV %{req.cltv_score*100:.0f}) — tam iade.")
        elif req.product_cost > 0 and req.product_cost + REPLACE_SHIPPING_COST < req.claimed_amount * 0.65:
            rules.append("RULE_STRONG_CASE_CHEAP_REPLACE")
            chosen = "REPLACE"
            rationale = ("Güçlü kanıt ama düşük değerli müşteri — değiştirme "
                          f"({req.product_cost + REPLACE_SHIPPING_COST:.0f} TL) "
                          f"refund'tan ucuz.")
        else:
            rules.append("RULE_STRONG_CASE_LOW_CLTV_REFUND")
            chosen = "REFUND"
            rationale = ("Güçlü kanıt — değiştirme maliyeti iadeyle yakın, "
                          "iade tercih.")
    elif req.evidence_score <= 0.30:
        if req.cltv_score >= 0.60:
            rules.append("RULE_WEAK_EVIDENCE_LOYAL_GOODWILL")
            chosen = "GOODWILL"
            rationale = (f"Zayıf kanıt + sadık müşteri (CLTV %{req.cltv_score*100:.0f}) — "
                          f"iyi niyet jesti.")
        else:
            rules.append("RULE_WEAK_EVIDENCE_LOW_CLTV_REJECT")
            chosen = "REJECT"
            rationale = (f"Zayıf kanıt (%{req.evidence_score*100:.0f}) + "
                          f"düşük CLTV (%{req.cltv_score*100:.0f}) — talep reddi.")
    else:
        rules.append("RULE_MID_EVIDENCE_PARTIAL")
        chosen = "PARTIAL"
        rationale = (f"Orta kanıt (%{req.evidence_score*100:.0f}) — kısmi iade "
                       f"(%50 tutarında).")

    cost_optimal = min(actions.items(), key=lambda kv: kv[1].expected_cost)
    if cost_optimal[0] != chosen:
        rule_cost_diff = actions[chosen].expected_cost - cost_optimal[1].expected_cost
        rules.append(f"RULE_PREFERRED_OVER_COST_OPTIMAL_{cost_optimal[0]}_"
                      f"DELTA_{rule_cost_diff:.2f}")

    return ADRDecision(
        recommended_action=chosen,
        expected_cost=float(actions[chosen].expected_cost),
        rationale=rationale,
        decision_matrix=matrix,
        rules_applied=rules,
    )


async def persist_case(req: ADRCaseRequest) -> ADRCaseOut:
    decision = recommend(req)
    async with AsyncSessionLocal() as session:
        row = ADRCase(
            order_id=req.order_id,
            customer_id=req.customer_id,
            dispute_type=req.dispute_type,
            claimed_amount=float(req.claimed_amount),
            evidence_score=float(req.evidence_score),
            cltv_score=float(req.cltv_score),
            repeat_risk=float(req.repeat_risk),
            decision_matrix={
                "matrix":        decision.decision_matrix,
                "rules":         decision.rules_applied,
                "rationale":     decision.rationale,
                "recommended":   decision.recommended_action,
            },
            recommended_action=decision.recommended_action,
            expected_cost=float(decision.expected_cost),
            settled=False,
            settled_at=None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return ADRCaseOut.model_validate(row)


async def mark_settled(case_id: int) -> Optional[ADRCaseOut]:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(ADRCase).where(ADRCase.id == case_id))).scalar_one_or_none()
        if row is None:
            return None
        row.settled = True
        row.settled_at = datetime.utcnow()
        await session.commit()
        await session.refresh(row)
        return ADRCaseOut.model_validate(row)


async def summary_by_action(days: int = 30) -> dict:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ADRCase.recommended_action,
                    func.count(ADRCase.id),
                    func.sum(ADRCase.expected_cost),
                    func.avg(ADRCase.claimed_amount))
            .group_by(ADRCase.recommended_action))).all()
    out = {}
    total_n = 0
    total_cost = 0.0
    for action, cnt, exp_cost, avg_claim in rows:
        cnt = int(cnt or 0)
        exp_cost = float(exp_cost or 0.0)
        out[action] = {
            "count":         cnt,
            "total_cost":    exp_cost,
            "avg_claim":     float(avg_claim or 0.0),
        }
        total_n += cnt
        total_cost += exp_cost
    return {"by_action": out, "total_cases": total_n, "total_cost": total_cost}


__all__ = [
    "ActionEvaluation", "ADRDecision",
    "evaluate_all_actions", "recommend",
    "persist_case", "mark_settled", "summary_by_action",
]
