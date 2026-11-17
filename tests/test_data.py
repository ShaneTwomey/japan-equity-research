from datetime import date
from shutil import copytree

import pandas as pd
import pytest

from research.data import DATA_DIR, following_annual_period, load_dataset, normalized_value
from research.model import compute_history


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("120,000", "千円", 120.0),
        ("2.5", "億円", 250.0),
        ("-4", "百万円", -4.0),
        ("1,000,000", "JPY", 1.0),
    ],
)
def test_japanese_amount_units(raw, unit, expected):
    assert normalized_value("operating_profit", raw, unit) == expected


def test_sign_and_stock_split_conventions():
    assert normalized_value("ppe_capex", "(1,127)", "百万円") == 1127
    assert normalized_value("intangible_capex", "-43", "百万円") == 43
    assert normalized_value("short_borrowings", "－", "百万円") == 0
    assert normalized_value("basic_eps", "119.80", "JPY/share", 2) == 59.90
    assert normalized_value("weighted_shares", "248,284,230", "shares", 2) == 496.56846
    with pytest.raises(ValueError):
        normalized_value("revenue", "85", "shares")
    with pytest.raises(ValueError):
        normalized_value("ppe_capex", "85", "百万円")


def test_five_annual_periods_and_independent_totals(dataset, histories):
    uss, mono = histories["4732"], histories["3064"]
    assert len(uss) == len(mono) == 5
    assert uss.iloc[-1][["start", "end"]].tolist() == ["2025-04-01", "2026-03-31"]
    assert mono.iloc[-1][["start", "end"]].tolist() == ["2025-01-01", "2025-12-31"]
    assert uss.iloc[-1]["cash_after_capex"] == 43_913 - 9_353 - 1_685
    assert mono.iloc[-1]["cash_after_capex"] == 33_726 - 11_938 - 4_131
    assert uss.iloc[-1]["net_debt"] == 697 + 1320 + 50 + 30 - 88_933
    assert mono.iloc[-1]["net_debt"] == 109 + 13_000 + 877 + 4 - 46_995
    assert dataset.provenance("4732")["url"].str.startswith("https://www.ussnet.co.jp/").all()


def test_eps_uses_weighted_shares_and_does_not_double_adjust(histories):
    uss = histories["4732"]
    assert uss.iloc[2]["weighted_shares"] == pytest.approx(481.916335)
    assert uss.iloc[2]["basic_eps"] == 68.28
    assert uss.iloc[-1]["recomputed_eps"] == pytest.approx(41_360 / 465.851381)
    for history in histories.values():
        assert history["eps_check"].eq("Within rounding tolerance").all()


def test_source_dashes_and_undisclosed_lines_are_distinct(histories):
    mono = histories["3064"]
    assert pd.isna(mono.iloc[0]["short_borrowings"])
    assert mono.iloc[0]["gross_debt"] == 9000 + 34 + 586
    assert mono.iloc[-1]["current_long_borrowings"] == 0


def test_incomplete_inputs_do_not_make_a_complete_derived_value(dataset, monkeypatch):
    gaps = dataset.facts.loc[
        ~(
            (dataset.facts["code"] == "4732")
            & (dataset.facts["end"] == "2026-03-31")
            & (dataset.facts["metric"] == "intangible_capex")
        )
    ]
    monkeypatch.setattr(dataset, "facts", gaps)
    latest = compute_history(dataset, "4732").iloc[-1]
    assert pd.isna(latest["cash_capex"])
    assert pd.isna(latest["cash_after_capex"])


def test_nonconsecutive_growth_unavailable(dataset, monkeypatch):
    monkeypatch.setattr(
        dataset, "periods", dataset.periods.loc[dataset.periods["end"] != "2025-03-31"]
    )
    assert pd.isna(compute_history(dataset, "4732").iloc[-1]["revenue_growth"])


def test_unexplained_eps_difference_is_visible(dataset, monkeypatch):
    facts = dataset.facts.copy()
    entry = facts["end"].eq("2026-03-31") & facts["metric"].eq("basic_eps")
    facts.loc[entry, "normalized_value"] = 1
    monkeypatch.setattr(dataset, "facts", facts)
    assert compute_history(dataset, "4732").iloc[-1]["eps_check"] == "Unexplained difference"


@pytest.mark.parametrize(
    ("file", "field", "value", "error"),
    [
        ("facts.csv", "source_id", "mono-2025", "Untraceable"),
        ("facts.csv", "normalized_value", "900000", "Normalization mismatch"),
        ("facts.csv", "source_share_basis", "unknown", "Incompatible share basis"),
        ("periods.csv", "start", "2021-05-01", "Invalid annual period"),
        ("periods.csv", "debt_components", "short_borrowings", "Incomplete debt components"),
    ],
)
def test_csv_validation_rejects_corrupt_data(tmp_path, file, field, value, error):
    root = tmp_path / "data"
    copytree(DATA_DIR, root)
    path = root / file
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    row = (
        frame.index[frame["metric"].eq("weighted_shares")][0]
        if field == "source_share_basis"
        else 0
    )
    frame.loc[row, field] = value
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match=error):
        load_dataset(root)


def test_next_fiscal_period_boundaries():
    assert following_annual_period(date(2026, 3, 31)) == (date(2026, 4, 1), date(2027, 3, 31))
    assert following_annual_period(date(2023, 12, 31)) == (date(2024, 1, 1), date(2024, 12, 31))
    assert following_annual_period(date(2023, 2, 28)) == (date(2023, 3, 1), date(2024, 2, 29))
