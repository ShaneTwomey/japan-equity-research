"""Create one research snapshot for the application, CSV files, and report."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from research.data import LABELS, Dataset, following_annual_period, unit
from research.model import PRICE_LABEL, SCENARIO_NAMES, forecast, sensitivity
from research.state import Workspace

HISTORY_FIELDS = (
    "revenue",
    "revenue_growth",
    "operating_profit",
    "operating_margin",
    "attributable_profit",
    "net_margin",
    "basic_eps",
    "weighted_shares",
    "operating_cash_flow",
    "cash_capex",
    "cash_after_capex",
    "cash",
    "gross_debt",
    "net_debt",
)
METHOD = (
    "Revenue growth divides the current comparable full-year revenue by the prior full-year "
    "revenue and subtracts one. The two margins divide operating profit and attributable profit "
    "by revenue, respectively.",
    "Cash capex is cash paid for property, plant and equipment plus intangible assets. "
    "Cash flow after capital expenditure is operating cash flow minus those purchases.",
    "Interest-bearing debt sums separately disclosed borrowings, bonds and recognized lease "
    "liabilities where applicable. Net debt subtracts closing cash and cash equivalents. "
    "The scope excludes unrecognized lease commitments and unclassified other liabilities.",
    "EPS reconciliation divides attributable profit by weighted-average ordinary shares. "
    "Allowed rounding is JPY 0.005 plus JPY 1 million divided by the weighted-average shares.",
    "Forecast revenue = base revenue × (1 + revenue growth).",
    "Forecast attributable profit = forecast revenue × attributable net margin.",
    "Forecast basic EPS = forecast attributable profit ÷ projected weighted-average ordinary shares.",
    f"{PRICE_LABEL}. P/E valuation is unavailable when forecast EPS is zero or negative.",
    "Price upside/downside = implied price ÷ manual reference share price − 1. The price "
    "comparison excludes dividends and does not establish a holding period.",
    "Sensitivity varies attributable net margin by up to ±2 percentage points and the multiple "
    "from 60% to 140% of the selected scenario, holding forecast growth and shares fixed.",
)
GAPS = (
    "The oldest fiscal year has no growth comparison in the bundled data.",
    "MonotaRO's Japanese December 2022 release reports that adopting the revenue recognition "
    "standard had no effect on profit or loss. The February 3, 2023 correction affects "
    "financing cash flow line labels and standalone income, outside the selected metrics.",
    "A balance-sheet line missing from a release is left blank in the component data. "
    "A dash on a reported line is preserved in provenance and treated as nil. Debt totals use "
    "the reviewed set of separately identified balance-sheet lines.",
    "The issuer translations report financial amounts rounded down to millions of yen. "
    "The historical view uses current-year releases and identifies split normalization explicitly.",
    "This offline dataset contains annual statements. Reference prices are manual inputs. "
    "Scenario prices and rationales are research assumptions.",
)
COMPARABILITY = (
    "USS's fiscal year ends in March and MonotaRO's ends in December. Each point uses the "
    "issuer’s own annual window. USS earns auction fees alongside resale and recycling. "
    "MonotaRO sells goods and incurs inventory and fulfillment costs. Differences in revenue "
    "recognition, business mix and capital needs affect direct margin and cash-flow comparisons."
)


def tokyo_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def historical_table(history: pd.DataFrame) -> pd.DataFrame:
    table = history[["start", "end", *HISTORY_FIELDS, "release", "version"]].copy()
    for field in ("revenue_growth", "operating_margin", "net_margin"):
        table[field] *= 100
    return table.rename(
        columns={
            **{field: f"{LABELS[field]} ({unit(field)})" for field in HISTORY_FIELDS},
            "start": "Fiscal start",
            "end": "Fiscal end",
            "release": "Annual release ID",
            "version": "Financial version",
        }
    )


@dataclass(frozen=True)
class Analysis:
    workspace: Workspace
    base_start: str
    base_end: str
    base_revenue: float
    base_source: str
    base_locator: str
    share_basis: str
    forecast_start: str
    forecast_end: str
    assumptions: pd.DataFrame
    results: pd.DataFrame
    sensitivity: pd.DataFrame
    coverage_notice: str


def analyze(dataset: Dataset, history: pd.DataFrame, workspace: Workspace, as_of=None) -> Analysis:
    base = history.loc[history["end"].eq(workspace.base_end)].iloc[0]
    start, end = following_annual_period(date.fromisoformat(base["end"]))
    basis = dataset.companies[workspace.company]["share_basis"]
    facts = dataset.facts
    revenue_fact = facts.loc[
        facts["code"].eq(workspace.company)
        & facts["end"].eq(workspace.base_end)
        & facts["metric"].eq("revenue")
    ].iloc[0]
    inputs, outputs = [], []
    base_revenue = float(base["revenue"])
    for case in SCENARIO_NAMES:
        assumption = workspace.scenarios[case]
        result = forecast(base_revenue, assumption, basis, workspace.reference)
        inputs.append(
            (
                case,
                assumption.growth * 100,
                assumption.margin * 100,
                assumption.shares,
                assumption.pe,
                assumption.rationale,
            )
        )
        outputs.append(
            (
                case,
                result.revenue,
                result.profit,
                result.eps,
                assumption.pe,
                result.price,
                result.upside * 100 if result.upside is not None else None,
                result.valuation_status,
            )
        )
    assumptions = pd.DataFrame(
        inputs,
        columns=[
            "Scenario",
            "Revenue growth (%)",
            "Attributable net margin (%)",
            "Weighted-average shares (million)",
            "Assumed forward P/E (×)",
            "Rationale",
        ],
    )
    results = pd.DataFrame(
        outputs,
        columns=[
            "Scenario",
            "Forecast revenue (JPYm)",
            "Forecast attributable profit (JPYm)",
            "Forecast basic EPS (JPY/share)",
            "Assumed forward P/E (×)",
            "Implied price (JPY/share)",
            "Price upside/downside (%)",
            "Valuation status",
        ],
    )
    notice = ""
    if end.isoformat() in set(history["end"]):
        notice = "A reported actual for this forecast period exists. This is a historical scenario exercise."
    elif end < (as_of or tokyo_today()):
        notice = "The forecast fiscal year has ended. The bundled annual coverage does not contain its actuals."
    elif base["end"] != history.iloc[-1]["end"]:
        notice = "The selected base predates the most recent bundled annual release."
    return Analysis(
        workspace,
        base["start"],
        base["end"],
        base_revenue,
        revenue_fact["source_id"],
        revenue_fact["locator"],
        basis,
        start.isoformat(),
        end.isoformat(),
        assumptions,
        results,
        sensitivity(base_revenue, workspace.scenarios[workspace.sensitivity_case], basis),
        notice,
    )


def sensitivity_grid(analysis: Analysis) -> pd.DataFrame:
    return analysis.sensitivity.pivot(
        index="Attributable net margin (%)", columns="Forward P/E (×)", values="JPY/share"
    )
