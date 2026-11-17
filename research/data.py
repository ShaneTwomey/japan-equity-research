"""Load and validate the bundled annual statements and their source registry."""

import json
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
AMOUNT_UNITS = {"JPY": 1e-6, "千円": 1e-3, "百万円": 1.0, "億円": 100.0, "JPYm": 1.0}
LABELS = {
    "revenue": "Revenue",
    "operating_profit": "Operating profit",
    "attributable_profit": "Attributable net profit",
    "basic_eps": "Reported basic EPS, normalized basis",
    "weighted_shares": "Weighted-average ordinary shares",
    "operating_cash_flow": "Operating cash flow",
    "ppe_capex": "Cash purchases of property, plant and equipment",
    "intangible_capex": "Cash purchases of intangible assets",
    "cash": "Cash and cash equivalents",
    "short_borrowings": "Short-term borrowings",
    "current_long_borrowings": "Current portion of long-term borrowings",
    "long_borrowings": "Noncurrent borrowings",
    "current_leases": "Current lease liabilities",
    "noncurrent_leases": "Noncurrent lease liabilities",
    "bonds": "Bonds payable, current and noncurrent",
    "revenue_growth": "Revenue growth, YoY",
    "operating_margin": "Operating margin",
    "net_margin": "Attributable net margin",
    "cash_capex": "Cash capital expenditure",
    "cash_after_capex": "Cash flow after capital expenditure",
    "gross_debt": "Interest-bearing debt incl. disclosed leases",
    "net_debt": "Net debt incl. disclosed leases",
    "recomputed_eps": "Recomputed EPS",
}
DEBT = (
    "short_borrowings",
    "current_long_borrowings",
    "long_borrowings",
    "current_leases",
    "noncurrent_leases",
    "bonds",
)
CAPEX = ("ppe_capex", "intangible_capex")
RAW_METRICS = tuple(LABELS)[:15]
PERIOD_COLUMNS = (
    "code",
    "start",
    "end",
    "reporting",
    "accounting",
    "release",
    "version",
    "share_basis",
    "debt_scope",
    "debt_components",
    "growth_comparable",
    "note",
)
VALUE_COLUMNS = (
    "code",
    "end",
    "metric",
    "source_id",
    "locator",
    "original_value",
    "original_unit",
    "split_factor",
    "source_share_basis",
    "normalized_value",
    "note",
)


def unit(metric: str) -> str:
    if metric in ("basic_eps", "recomputed_eps"):
        return "JPY/share"
    if metric == "weighted_shares":
        return "million shares"
    if metric in ("revenue_growth", "operating_margin", "net_margin"):
        return "%"
    return "JPYm"


def original_number(original: str) -> float:
    if original in {"-", "－", "—", "–"}:
        return 0.0
    value = original.replace(",", "")
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    result = float(value)
    if not isfinite(result):
        raise ValueError("A source amount must be finite.")
    return result


def normalized_value(
    metric: str, original: str, original_unit: str, split_factor: float = 1
) -> float:
    value = original_number(original)
    if not isfinite(split_factor) or split_factor <= 0:
        raise ValueError("Split factor must be positive.")
    if metric == "basic_eps" and original_unit == "JPY/share":
        return value / split_factor
    if metric == "weighted_shares" and original_unit == "shares":
        return value / 1_000_000 * split_factor
    if metric in RAW_METRICS and metric not in {"basic_eps", "weighted_shares"}:
        if original_unit in AMOUNT_UNITS and split_factor == 1:
            result = value * AMOUNT_UNITS[original_unit]
            if metric in CAPEX:
                if result > 0:
                    raise ValueError("Cash purchases must have an outflow sign in the source.")
                return -result if result else 0.0
            return result
    raise ValueError(f"Unsupported units or split adjustment for {metric}: {original_unit}")


def valid_url(value: str) -> bool:
    url = urlsplit(value)
    return url.scheme == "https" and bool(url.hostname) and not (url.username or url.password)


def following_annual_period(end: date) -> tuple[date, date]:
    """Shift a full fiscal year by one year, including leap-year February year-ends."""
    forecast_start = end + pd.Timedelta(days=1)
    return forecast_start, (forecast_start + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date()


@dataclass
class Dataset:
    companies: dict
    sources: dict
    periods: pd.DataFrame
    facts: pd.DataFrame

    def history(self, code: str) -> pd.DataFrame:
        """One annual row per period, with absent inputs represented by NaN."""
        periods = self.periods.loc[self.periods["code"].eq(code)].set_index("end")
        raw = self.facts[self.facts["code"].eq(code)]
        values = raw.pivot(index="end", columns="metric", values="normalized_value")
        return periods.join(values.reindex(columns=RAW_METRICS)).reset_index()

    def provenance(self, code: str) -> pd.DataFrame:
        facts = self.facts.loc[self.facts["code"].eq(code)].copy()
        facts.insert(1, "company", self.companies[code]["name"])
        facts = facts.merge(
            self.periods.drop(columns=["note", "release"]), on=["code", "end"], how="left"
        )
        for field in ("title", "url", "published", "retrieved"):
            facts[field] = facts["source_id"].map(lambda key: self.sources[key][field])
        facts["normalized_unit"] = facts["metric"].map(unit)
        return facts.drop(columns=["growth_comparable", "debt_scope", "debt_components"])


def _load_csv(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    result = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    if tuple(result.columns) != columns:
        raise ValueError(f"Unexpected columns in {path.name}.")
    return result


def load_dataset(root: Path = DATA_DIR) -> Dataset:
    companies = json.loads((root / "companies.json").read_text(encoding="utf-8"))
    sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    periods = _load_csv(root / "periods.csv", PERIOD_COLUMNS)
    facts = _load_csv(root / "facts.csv", VALUE_COLUMNS)

    for source_id, source in sources.items():
        retrieved = date.fromisoformat(source["retrieved"])
        published = date.fromisoformat(source["published"]) if source["published"] else None
        if (
            not source["title"]
            or not valid_url(source["url"])
            or source["code"] not in companies
            or (published and published > retrieved)
        ):
            raise ValueError(f"Invalid registry source: {source_id}")
    for code, company in companies.items():
        if not any(periods["code"].eq(code)):
            raise ValueError(f"{code} needs an annual period.")
        for source_id in company["business_sources"] + company["context_sources"]:
            if source_id not in sources or sources[source_id]["code"] != code:
                raise ValueError(f"Invalid company source: {source_id}")

    if (
        periods.duplicated(["code", "end"]).any()
        or facts.duplicated(["code", "end", "metric"]).any()
    ):
        raise ValueError("Duplicate company fiscal period or reported metric.")
    by_period = {}
    for row in periods.itertuples(index=False):
        start, end = date.fromisoformat(row.start), date.fromisoformat(row.end)
        next_start, _ = following_annual_period(end)
        release = sources.get(row.release, {})
        if (
            not 364 <= (end - start).days <= 365
            or (start + pd.DateOffset(years=1)).date() != next_start
            or row.code not in companies
            or row.reporting != "Consolidated"
            or not row.accounting
            or row.version not in ("As released", "Restated")
            or row.share_basis != companies[row.code]["share_basis"]
            or row.growth_comparable not in ("yes", "no")
            or row.debt_scope not in ("complete", "unconfirmed")
            or release.get("code") != row.code
            or not release.get("published")
            or date.fromisoformat(release["published"]) < end
        ):
            raise ValueError(f"Invalid annual period: {row.code} {row.end}")
        by_period[(row.code, row.end)] = row

    for row in facts.itertuples(index=False):
        period = by_period.get((row.code, row.end))
        source = sources.get(row.source_id, {})
        factor = float(row.split_factor)
        if (
            not period
            or source.get("code") != row.code
            or not source.get("published")
            or date.fromisoformat(source["published"]) < date.fromisoformat(row.end)
            or not row.locator
            or row.metric not in RAW_METRICS
        ):
            raise ValueError(f"Untraceable fact: {row.code} {row.end} {row.metric}")
        if row.metric in {"basic_eps", "weighted_shares"}:
            expected = companies[row.code]["split_factors"].get(row.source_share_basis)
            if (
                expected is None
                or factor != expected
                or (factor == 1) != (row.source_share_basis == period.share_basis)
                or not row.note
            ):
                raise ValueError(f"Incompatible share basis: {row.code} {row.end} {row.metric}")
        elif row.source_share_basis:
            raise ValueError("A non-share fact must have an empty source share basis.")
        computed = normalized_value(row.metric, row.original_value, row.original_unit, factor)
        if abs(computed - float(row.normalized_value)) > 1e-8 or not isfinite(
            float(row.normalized_value)
        ):
            raise ValueError(f"Normalization mismatch: {row.code} {row.end} {row.metric}")
        if row.metric in (*DEBT, "revenue", "cash") and computed < 0:
            raise ValueError(f"Negative financial balance: {row.metric}")
        if row.metric == "weighted_shares" and computed <= 0:
            raise ValueError("Weighted-average shares must be positive.")

    for (code, end), period in by_period.items():
        if period.debt_scope == "complete":
            disclosed = set(period.debt_components.split(";"))
            selected = facts["code"].eq(code) & facts["end"].eq(end) & facts["metric"].isin(DEBT)
            if disclosed != set(facts.loc[selected, "metric"]) or not disclosed <= set(DEBT):
                raise ValueError(f"Incomplete debt components: {code} {end}.")
    facts["normalized_value"] = facts["normalized_value"].astype(float)
    return Dataset(companies, sources, periods.sort_values(["code", "end"]), facts)
