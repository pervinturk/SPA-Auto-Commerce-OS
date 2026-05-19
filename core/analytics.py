"""Industrial-engineering style analytics: MRP, importance ranking,
forecasting, supplier health scoring. All math, no external ML deps."""
import math
from typing import List, Tuple

Z_SCORE = {0.90: 1.28, 0.95: 1.65, 0.97: 1.88, 0.98: 2.05, 0.99: 2.33}


def moving_average(series: List[float], window: int = 3) -> List[float]:
    if not series:
        return []
    out = []
    for i in range(len(series)):
        s = series[max(0, i - window + 1): i + 1]
        out.append(sum(s) / len(s))
    return out


def linear_trend(series: List[float]) -> Tuple[float, float]:
    n = len(series)
    if n < 2:
        return 0.0, (series[0] if series else 0.0)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(series) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, series))
    den = sum((x - mx) ** 2 for x in xs) or 1
    slope = num / den
    intercept = my - slope * mx
    return slope, intercept


def forecast(series: List[float], horizon: int = 3) -> List[float]:
    if not series:
        return [0.0] * horizon
    slope, intercept = linear_trend(series)
    base = sum(series[-3:]) / min(3, len(series))
    out = []
    n = len(series)
    for h in range(1, horizon + 1):
        trend_v = slope * (n + h - 1) + intercept
        v = 0.6 * trend_v + 0.4 * base
        out.append(max(0.0, v))
    return out


def std(series: List[float]) -> float:
    if len(series) < 2:
        return 0.0
    m = sum(series) / len(series)
    return math.sqrt(sum((x - m) ** 2 for x in series) / (len(series) - 1))


def reorder_point(avg_daily_demand: float, lead_time_days: float,
                  demand_std: float, service_level: float = 0.95) -> float:
    z = Z_SCORE.get(round(service_level, 2), 1.65)
    safety = z * demand_std * math.sqrt(max(lead_time_days, 0))
    return avg_daily_demand * lead_time_days + safety


def eoq(annual_demand: float, ordering_cost: float = 250.0,
        holding_cost_per_unit_per_year: float = 12.0) -> float:
    if annual_demand <= 0 or holding_cost_per_unit_per_year <= 0:
        return 0.0
    return math.sqrt((2 * annual_demand * ordering_cost) / holding_cost_per_unit_per_year)


def mrp_report(product: dict) -> dict:
    sales = product.get("monthly_sales", []) or []
    avg_monthly = sum(sales[-6:]) / max(1, len(sales[-6:])) if sales else 0
    avg_daily = avg_monthly / 30.0
    monthly_std = std(sales[-6:]) if len(sales) >= 2 else 0
    daily_std = monthly_std / math.sqrt(30) if monthly_std else 0
    lead = product.get("lead_time", 5)

    rop = reorder_point(avg_daily, lead, daily_std, 0.95)
    annual = avg_monthly * 12
    eoq_qty = eoq(annual)

    stock = product.get("stock", 0)
    days_left = stock / avg_daily if avg_daily > 0 else 999
    reorder_by_days = max(0, days_left - lead)

    suggested_qty = max(int(math.ceil(eoq_qty)), int(rop) - stock,
                        product.get("reorder_qty", 0))
    return {
        "avg_daily_demand": avg_daily,
        "avg_monthly_demand": avg_monthly,
        "demand_std_monthly": monthly_std,
        "lead_time": lead,
        "safety_stock": Z_SCORE[0.95] * daily_std * math.sqrt(lead),
        "reorder_point": rop,
        "eoq": eoq_qty,
        "days_of_stock_left": days_left,
        "reorder_by_days": reorder_by_days,
        "suggested_qty": suggested_qty,
        "estimated_cost": suggested_qty * product.get("cost", 0),
        "service_level": 0.95,
        "is_critical": stock <= rop,
    }


def importance_score(product: dict) -> float:
    """Composite importance: revenue contribution (60%) + margin (20%) +
    stockout risk (20%). Higher = more attention required."""
    sales = product.get("monthly_sales", []) or [0]
    avg_monthly = sum(sales[-3:]) / max(1, len(sales[-3:]))
    revenue_contrib = avg_monthly * product.get("price", 0)
    margin = ((product.get("price", 0) - product.get("cost", 0)) /
              max(product.get("price", 1), 1))

    avg_daily = avg_monthly / 30.0
    stock = product.get("stock", 0)
    days_left = stock / avg_daily if avg_daily > 0 else 999
    risk = max(0.0, min(1.0, (product.get("lead_time", 5) + 3 - days_left) / 10))

    rev_norm = min(1.0, revenue_contrib / 80000)
    return 0.60 * rev_norm + 0.20 * margin + 0.20 * risk


def abc_class(score: float) -> str:
    if score >= 0.55:
        return "A"
    if score >= 0.30:
        return "B"
    return "C"


def supplier_health(supplier: dict) -> dict:
    on_time = supplier.get("on_time_rate", 0)
    defect = supplier.get("defect_rate", 0)
    lead_t = supplier.get("lead_time_target", 0) or 1
    lead_a = supplier.get("lead_time_actual", lead_t)
    lead_perf = max(0.0, 1 - max(0.0, (lead_a - lead_t) / lead_t))

    score = 0.45 * on_time + 0.30 * (1 - min(defect, 1)) + 0.25 * lead_perf
    if score >= 0.85:
        rating, color = "A — Mukemmel", "#10B981"
    elif score >= 0.70:
        rating, color = "B — İyi", "#22C55E"
    elif score >= 0.55:
        rating, color = "C — Orta", "#F59E0B"
    else:
        rating, color = "D — Riskli", "#EF4444"

    lost = 0
    if on_time < 0.85:
        lost += supplier.get("total_orders", 0) * (0.85 - on_time) * 180
    if defect > 0.02:
        lost += supplier.get("total_orders", 0) * defect * 500

    gained = supplier.get("total_orders", 0) * on_time * 90
    return {
        "score": score,
        "rating": rating,
        "color": color,
        "on_time": on_time,
        "defect": defect,
        "lead_perf": lead_perf,
        "estimated_lost_revenue": lost,
        "estimated_value_added": gained,
    }


def order_breakdown(order: dict, product_cost: float = 0) -> dict:
    total = order.get("total", 0)
    commission_rate = order.get("commission", 0)
    kdv_rate = order.get("kdv", 0.20)
    cargo = order.get("cargo_cost", 0)

    commission = total * commission_rate
    kdv = total - (total / (1 + kdv_rate))
    net_revenue = total - commission - kdv - cargo
    cost = product_cost * order.get("qty", 1)
    net_profit = net_revenue - cost
    margin = (net_profit / total * 100) if total else 0
    return {
        "total": total,
        "commission_rate": commission_rate,
        "commission": commission,
        "kdv_rate": kdv_rate,
        "kdv": kdv,
        "cargo": cargo,
        "product_cost": cost,
        "net_revenue": net_revenue,
        "net_profit": net_profit,
        "margin_pct": margin,
    }


def parameter_simulation(product: dict, price_delta_pct: float = 0,
                          ad_spend_delta_pct: float = 0) -> dict:
    sales = product.get("monthly_sales", []) or [0]
    base_qty = sum(sales[-3:]) / max(1, len(sales[-3:]))
    base_price = product.get("price", 0)
    base_cost = product.get("cost", 0)

    elasticity = -1.2
    qty_change_from_price = elasticity * (price_delta_pct / 100)
    qty_change_from_ads = 0.35 * (ad_spend_delta_pct / 100)
    new_qty = base_qty * (1 + qty_change_from_price + qty_change_from_ads)
    new_price = base_price * (1 + price_delta_pct / 100)

    base_revenue = base_qty * base_price
    base_profit = base_qty * (base_price - base_cost)
    new_revenue = new_qty * new_price
    new_profit = new_qty * (new_price - base_cost)

    return {
        "base_qty": base_qty,
        "new_qty": new_qty,
        "base_revenue": base_revenue,
        "new_revenue": new_revenue,
        "base_profit": base_profit,
        "new_profit": new_profit,
        "revenue_delta": new_revenue - base_revenue,
        "profit_delta": new_profit - base_profit,
        "qty_delta_pct": (new_qty / base_qty - 1) * 100 if base_qty else 0,
    }
