"""Historical ratios, annual earnings forecasts, and P/E sensitivity."""

from dataclasses import dataclass, replace
from datetime import date
from itertools import product
from math import isfinite

import pandas as pd

from research.data import CAPEX, DEBT, Dataset

SCENARIO_NAMES = ("Bear", "Base", "Bull")
PRICE_LABEL = "Implied price: forecast EPS × assumed forward P/E"
MAX_AMOUNT = 1e12
MIN_POSITIVE = 1e-6


def compute_history(dataset: Dataset, code: str) -> pd.DataFrame:
    history = dataset.history(code)
    revenue = history["revenue"].where(history["revenue"].gt(0))
    prev_end = pd.to_datetime(history["end"]).shift()
    contiguous = (pd.to_datetime(history["start"]) - prev_end).dt.days.eq(1)
    comparable = (
        contiguous
        & history["growth_comparable"].eq("yes")
        & history["accounting"].eq(history["accounting"].shift())
        & history["reporting"].eq(history["reporting"].shift())
    )
    history["revenue_growth"] = (revenue / revenue.shift() - 1).where(comparable)
    history["operating_margin"] = history["operating_profit"] / revenue
    history["net_margin"] = history["attributable_profit"] / revenue
    history["cash_capex"] = history[list(CAPEX)].sum(axis=1, min_count=len(CAPEX))
    history["cash_after_capex"] = history["operating_cash_flow"] - history["cash_capex"]
    covered = history["debt_scope"].eq("complete")
    history["gross_debt"] = history[list(DEBT)].sum(axis=1, min_count=1).where(covered)
    history["net_debt"] = history["gross_debt"] - history["cash"]
    history["recomputed_eps"] = history["attributable_profit"] / history["weighted_shares"]
    history["eps_tolerance"] = 0.005 + 1 / history["weighted_shares"]
    history["eps_difference"] = history["recomputed_eps"] - history["basic_eps"]
    history["eps_check"] = "Unavailable"
    available = history["eps_difference"].notna()
    matches = history["eps_difference"].abs().le(history["eps_tolerance"])
    history.loc[available & matches, "eps_check"] = "Within rounding tolerance"
    history.loc[available & ~matches, "eps_check"] = "Unexplained difference"
    return history


def _finite(value: float, label: str, low: float, high: float) -> None:
    if type(value) not in (float, int) or not low <= value <= high or not isfinite(value):
        raise ValueError(f"{label} must be finite and between {low:g} and {high:g}.")


@dataclass(frozen=True)
class Scenario:
    growth: float
    margin: float
    shares: float
    pe: float
    rationale: str

    def __post_init__(self):
        _finite(self.growth, "Revenue growth", -1, 100)
        _finite(self.margin, "Attributable net margin", -100, 100)
        _finite(self.shares, "Projected weighted-average shares", MIN_POSITIVE, MAX_AMOUNT)
        _finite(self.pe, "Forward P/E", MIN_POSITIVE, MAX_AMOUNT)
        if not isinstance(self.rationale, str) or len(self.rationale) > 1600:
            raise ValueError("Scenario rationale must be text of up to 1,600 characters.")


@dataclass(frozen=True)
class ReferencePrice:
    price: float
    as_of: date
    source: str
    share_basis: str

    def __post_init__(self):
        _finite(self.price, "Reference price", MIN_POSITIVE, MAX_AMOUNT)
        if (
            type(self.as_of) is not date
            or not isinstance(self.source, str)
            or not self.source.strip()
            or len(self.source) > 300
        ):
            raise ValueError("Provide a reference date and a source of up to 300 characters.")
        if not isinstance(self.share_basis, str) or not self.share_basis:
            raise ValueError("Confirm the reference share basis.")


@dataclass(frozen=True)
class Forecast:
    revenue: float
    profit: float
    eps: float
    price: float | None
    upside: float | None
    valuation_status: str


def forecast(
    base_revenue: float,
    scenario: Scenario,
    share_basis: str,
    reference: ReferencePrice | None = None,
) -> Forecast:
    _finite(base_revenue, "Base revenue", 0, MAX_AMOUNT)
    if reference is not None and reference.share_basis != share_basis:
        raise ValueError("Reference share basis must match the projected EPS basis.")
    revenue = base_revenue * (1 + scenario.growth)
    profit = revenue * scenario.margin
    eps = profit / scenario.shares
    if not isfinite(eps):
        raise ValueError("Forecast EPS is out of range.")
    if eps <= 0:
        return Forecast(revenue, profit, eps, None, None, "P/E not meaningful for EPS ≤ 0")
    price = eps * scenario.pe
    upside = price / reference.price - 1 if reference is not None else None
    if not isfinite(price) or (upside is not None and not isfinite(upside)):
        raise ValueError("Valuation is out of range.")
    return Forecast(revenue, profit, eps, price, upside, "Meaningful")


def sensitivity(base_revenue: float, scenario: Scenario, share_basis: str) -> pd.DataFrame:
    """Five margin points and five positive P/E multiples centered on the assumptions."""
    margins = [
        scenario.margin + step / 100
        for step in (-2, -1, 0, 1, 2)
        if abs(scenario.margin + step / 100) <= 100
    ]
    multiples = [
        scenario.pe * scale
        for scale in (0.6, 0.8, 1, 1.2, 1.4)
        if MIN_POSITIVE <= scenario.pe * scale <= MAX_AMOUNT
    ]
    rows = []
    for margin, pe in product(margins, multiples):
        cell = replace(scenario, margin=margin, pe=pe)
        rows.append((margin * 100, pe, forecast(base_revenue, cell, share_basis).price))
    return pd.DataFrame(
        rows, columns=["Attributable net margin (%)", "Forward P/E (×)", "JPY/share"]
    )
