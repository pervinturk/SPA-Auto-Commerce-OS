from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import select

from core.database_async import (AsyncSessionLocal, ForexPosition,
                                    PortfolioDecision)
from core.schemas import (ForexPositionIn, ForexPositionOut,
                            PortfolioDecisionIn, PortfolioDecisionOut,
                            PortfolioCandidate)


SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / SQRT_2PI


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_inv_cdf(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        if p <= 0.0:
            return -8.0
        return 8.0
    a = [-3.969683028665376e+01,  2.209460984245205e+02,
          -2.759285104469687e+02,  1.383577518672690e+02,
          -3.066479806614716e+01,  2.506628277459239e+00]
    b = [-5.447609879822406e+01,  1.615858368580409e+02,
          -1.556989798598866e+02,  6.680131188771972e+01,
          -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
          -2.400758277161838e+00, -2.549732539343734e+00,
           4.374664141464968e+00,  2.938163982698783e+00]
    d = [ 7.784695709041462e-03,  3.224671290700398e-01,
           2.445134137142996e+00,  3.754408661907416e+00]
    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return ((((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5])
                / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0))
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return ((((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q
                / (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0))
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -((((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5])
              / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0))


def _stats(series: Sequence[float]) -> tuple[float, float]:
    n = len(series)
    if n == 0:
        return 0.0, 0.0
    mu = sum(series) / n
    if n < 2:
        return mu, 0.0
    var = sum((x - mu) ** 2 for x in series) / (n - 1)
    return mu, math.sqrt(max(0.0, var))


@dataclass
class VaRResult:
    pair:               str
    notional:           float
    horizon_days:       int
    confidence:         float
    mu_daily:           float
    sigma_daily:        float
    z_score:            float
    parametric_var:     float
    expected_shortfall: float
    hedge_recommended:  bool
    hedge_ratio:        float
    method:             str = "PARAMETRIC_BROWNIAN"

    def to_dict(self) -> dict:
        return {
            "pair":               self.pair,
            "notional":           self.notional,
            "horizon_days":       self.horizon_days,
            "confidence":         self.confidence,
            "mu_daily":           self.mu_daily,
            "sigma_daily":        self.sigma_daily,
            "z_score":            self.z_score,
            "parametric_var":     self.parametric_var,
            "expected_shortfall": self.expected_shortfall,
            "hedge_recommended":  self.hedge_recommended,
            "hedge_ratio":        self.hedge_ratio,
            "method":             self.method,
        }


def parametric_var(notional: float,
                     mu_daily: float,
                     sigma_daily: float,
                     horizon_days: int,
                     confidence: float = 0.99) -> float:
    if notional <= 0 or sigma_daily < 0 or horizon_days <= 0:
        return 0.0
    h = float(horizon_days)
    mu_t = mu_daily * h
    sigma_t = sigma_daily * math.sqrt(h)
    z = _norm_inv_cdf(confidence)
    loss = -mu_t * notional + z * sigma_t * notional
    return max(0.0, loss)


def expected_shortfall(notional: float,
                         mu_daily: float,
                         sigma_daily: float,
                         horizon_days: int,
                         confidence: float = 0.99) -> float:
    if notional <= 0 or sigma_daily <= 0 or horizon_days <= 0:
        return 0.0
    alpha = 1.0 - confidence
    if alpha <= 0:
        alpha = 1e-9
    h = float(horizon_days)
    mu_t = mu_daily * h
    sigma_t = sigma_daily * math.sqrt(h)
    z = _norm_inv_cdf(confidence)
    es = -mu_t * notional + sigma_t * notional * (_norm_pdf(z) / alpha)
    return max(0.0, es)


def hedge_advice(var_value: float, notional: float,
                   threshold_pct: float = 0.05) -> tuple[bool, float]:
    if notional <= 0 or var_value <= 0:
        return False, 0.0
    exposure_ratio = var_value / notional
    if exposure_ratio <= threshold_pct:
        return False, 0.0
    excess = exposure_ratio - threshold_pct
    ratio = min(1.0, max(0.0, excess / max(exposure_ratio, 1e-9)))
    return True, ratio


def compute_var(pair: str,
                  notional: float,
                  return_series: Sequence[float],
                  horizon_days: int = 10,
                  confidence: float = 0.99,
                  hedge_threshold_pct: float = 0.05) -> VaRResult:
    mu, sigma = _stats(return_series)
    z = _norm_inv_cdf(confidence)
    var = parametric_var(notional, mu, sigma, horizon_days, confidence)
    es = expected_shortfall(notional, mu, sigma, horizon_days, confidence)
    rec, ratio = hedge_advice(var, notional, hedge_threshold_pct)
    return VaRResult(
        pair=pair, notional=float(notional),
        horizon_days=int(horizon_days), confidence=float(confidence),
        mu_daily=float(mu), sigma_daily=float(sigma), z_score=float(z),
        parametric_var=float(var), expected_shortfall=float(es),
        hedge_recommended=bool(rec), hedge_ratio=float(ratio))


def rot(expected_return: float, lead_days: float,
          turnover_factor: float = 365.0) -> float:
    if lead_days <= 0:
        return 0.0
    cycles_per_year = turnover_factor / lead_days
    return expected_return * cycles_per_year


def sharpe_rot(expected_return: float, sigma: float, lead_days: float,
                 risk_free_rate: float = 0.0,
                 turnover_factor: float = 365.0) -> float:
    if sigma <= 0 or lead_days <= 0:
        return 0.0
    annual_rot = rot(expected_return, lead_days, turnover_factor)
    annual_sigma = sigma * math.sqrt(max(1.0, turnover_factor / lead_days))
    if annual_sigma <= 0:
        return 0.0
    return (annual_rot - risk_free_rate) / annual_sigma


@dataclass
class PortfolioResult:
    sku_universe:      list[str]
    rot_vector:        list[float]
    sharpe_rot_vector: list[float]
    selected_skus:     list[str]
    selected_weights:  list[float]
    expected_return:   float
    portfolio_sigma:   float
    risk_free_rate:    float
    method:            str = "SHARPE_ROT"

    def to_dict(self) -> dict:
        return {
            "sku_universe":      list(self.sku_universe),
            "rot_vector":        list(self.rot_vector),
            "sharpe_rot_vector": list(self.sharpe_rot_vector),
            "selected_skus":     list(self.selected_skus),
            "selected_weights":  list(self.selected_weights),
            "expected_return":   float(self.expected_return),
            "portfolio_sigma":   float(self.portfolio_sigma),
            "risk_free_rate":    float(self.risk_free_rate),
            "method":            self.method,
        }


def _inverse_variance_weights(sigmas: list[float]) -> list[float]:
    eps = 1e-8
    inv_var = [1.0 / max(s * s, eps) for s in sigmas]
    total = sum(inv_var)
    if total <= 0:
        n = len(sigmas)
        return [1.0 / n] * n
    return [iv / total for iv in inv_var]


def select_portfolio(candidates: Sequence[PortfolioCandidate],
                       risk_free_rate: float = 0.0,
                       top_k: int = 5,
                       method: str = "SHARPE_ROT") -> PortfolioResult:
    n = len(candidates)
    if n == 0:
        return PortfolioResult([], [], [], [], [], 0.0, 0.0, risk_free_rate, method)

    skus = [c.sku for c in candidates]
    rot_v = [rot(c.expected_return, c.avg_lead_days) for c in candidates]
    sharpe_v = [sharpe_rot(c.expected_return, c.sigma, c.avg_lead_days,
                              risk_free_rate) for c in candidates]

    ranking_key = sharpe_v if method.upper() == "SHARPE_ROT" else rot_v
    ranked = sorted(range(n), key=lambda i: -ranking_key[i])
    take = min(top_k, n)
    chosen = ranked[:take]

    chosen_sigmas = [candidates[i].sigma for i in chosen]
    weights = _inverse_variance_weights(chosen_sigmas)
    chosen_skus = [skus[i] for i in chosen]
    chosen_returns = [candidates[i].expected_return for i in chosen]

    port_return = sum(w * r for w, r in zip(weights, chosen_returns))
    port_var = sum((w * s) ** 2 for w, s in zip(weights, chosen_sigmas))
    port_sigma = math.sqrt(max(0.0, port_var))

    return PortfolioResult(
        sku_universe=skus,
        rot_vector=rot_v,
        sharpe_rot_vector=sharpe_v,
        selected_skus=chosen_skus,
        selected_weights=weights,
        expected_return=port_return,
        portfolio_sigma=port_sigma,
        risk_free_rate=risk_free_rate,
        method=method,
    )


async def persist_forex(req: ForexPositionIn) -> ForexPositionOut:
    result = compute_var(
        pair=req.pair, notional=float(req.notional),
        return_series=list(req.return_series),
        horizon_days=int(req.horizon_days),
        confidence=float(req.confidence),
        hedge_threshold_pct=float(req.auto_hedge_threshold_pct))
    async with AsyncSessionLocal() as session:
        row = ForexPosition(
            pair=result.pair,
            notional=result.notional,
            horizon_days=result.horizon_days,
            confidence=result.confidence,
            mu_daily=result.mu_daily,
            sigma_daily=result.sigma_daily,
            z_score=result.z_score,
            parametric_var=result.parametric_var,
            expected_shortfall=result.expected_shortfall,
            hedge_recommended=result.hedge_recommended,
            hedge_ratio=result.hedge_ratio,
            method=result.method,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return ForexPositionOut.model_validate(row)


async def persist_portfolio(req: PortfolioDecisionIn) -> PortfolioDecisionOut:
    result = select_portfolio(
        candidates=req.candidates,
        risk_free_rate=float(req.risk_free_rate),
        top_k=int(req.top_k),
        method=req.method)
    async with AsyncSessionLocal() as session:
        row = PortfolioDecision(
            sku_universe=result.sku_universe,
            rot_vector=result.rot_vector,
            sharpe_rot_vector=result.sharpe_rot_vector,
            risk_free_rate=result.risk_free_rate,
            selected_skus=result.selected_skus,
            selected_weights=result.selected_weights,
            expected_return=result.expected_return,
            portfolio_sigma=result.portfolio_sigma,
            method=result.method,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return PortfolioDecisionOut.model_validate(row)


async def latest_forex_for(pair: str) -> Optional[ForexPositionOut]:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(ForexPosition)
            .where(ForexPosition.pair == pair)
            .order_by(ForexPosition.created_at.desc())
            .limit(1))).scalar_one_or_none()
        if row is None:
            return None
        return ForexPositionOut.model_validate(row)


async def latest_portfolio() -> Optional[PortfolioDecisionOut]:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(PortfolioDecision)
            .order_by(PortfolioDecision.snapshot_at.desc())
            .limit(1))).scalar_one_or_none()
        if row is None:
            return None
        return PortfolioDecisionOut.model_validate(row)


__all__ = [
    "VaRResult", "PortfolioResult",
    "parametric_var", "expected_shortfall", "hedge_advice",
    "compute_var", "rot", "sharpe_rot", "select_portfolio",
    "persist_forex", "persist_portfolio",
    "latest_forex_for", "latest_portfolio",
]
