from dataclasses import replace
from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from research.analysis import analyze, sensitivity_grid
from research.export import csv_bytes, html_report, scenario_export
from research.model import ReferencePrice, Scenario, forecast
from research.state import default_workspace, load_workspace, reset_scenario, save_workspace

BASIS = "fixture"
STANDARD = Scenario(0.10, 0.10, 100, 20, "Hand check")
PRICE = ReferencePrice(2000, date(2025, 12, 31), "Test fixture", BASIS)


def test_hand_check():
    result = forecast(100_000, STANDARD, BASIS, PRICE)
    assert result.revenue == pytest.approx(110_000)
    assert result.profit == pytest.approx(11_000)
    assert result.eps == pytest.approx(110)
    assert result.price == pytest.approx(2200)
    assert result.upside == pytest.approx(0.10)


@pytest.mark.parametrize("margin", [0, -0.07])
def test_nonpositive_eps_suppresses_valuation_only(margin):
    result = forecast(100_000, replace(STANDARD, margin=margin), BASIS, PRICE)
    assert result.eps <= 0
    assert result.revenue > 0
    assert result.price is None and result.upside is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("growth", -1.01),
        ("margin", float("nan")),
        ("shares", 0),
        ("shares", -2),
        ("pe", 0),
        ("pe", float("inf")),
    ],
)
def test_invalid_scenario_inputs_are_rejected(field, value):
    with pytest.raises(ValueError):
        replace(STANDARD, **{field: value})


@pytest.mark.parametrize("price", [0, -100, float("inf")])
def test_invalid_reference_price(price):
    with pytest.raises(ValueError):
        replace(PRICE, price=price)


def test_reference_must_be_on_same_basis():
    with pytest.raises(ValueError, match="must match"):
        forecast(100_000, STANDARD, "other", PRICE)
    result = forecast(100_000, STANDARD, BASIS)
    assert result.price == pytest.approx(2200)
    assert result.upside is None


def test_older_year_forecast_is_flagged(dataset, histories):
    code = "4732"
    history = histories[code]
    workspace = default_workspace(code, dataset.companies[code], history)
    analysis = analyze(dataset, history, replace(workspace, base_end="2024-03-31"))
    assert analysis.forecast_end == "2025-03-31"
    assert "reported actual" in analysis.coverage_notice
    stale = analyze(dataset, history, workspace, as_of=date(2027, 5, 1))
    assert "has ended" in stale.coverage_notice


def test_export_matches_edited_assumptions_and_escapes_notes(dataset, histories):
    code = "3064"
    company, history = dataset.companies[code], histories[code]
    initial = default_workspace(code, company, history)
    ref = replace(PRICE, share_basis=company["share_basis"])
    edited = replace(
        initial,
        scenarios={**initial.scenarios, "Base": STANDARD},
        notes={**initial.notes, "thesis": '<img src=x onerror="alert(1)">'},
        reference=ref,
        notes_origin="Edited research notes",
    )
    analysis = analyze(dataset, history, edited)
    html = html_report(dataset, history, analysis).decode()
    assert "Hand check" in html
    assert "&lt;img" in html and "<img src=x" not in html
    assert "2025-12-31" in html and "2026-12-31" in html and "Test fixture" in html
    assert "mono-2022-policy" in html and "2025-12-31</summary>" in html
    export = pd.read_csv(BytesIO(csv_bytes(scenario_export(analysis))))
    price = 333_880 * 1.10 * 0.10 / 100 * 20
    assert export.loc[1, "Implied price (JPY/share)"] == pytest.approx(price)
    assert sensitivity_grid(analysis).loc[10, 20] == pytest.approx(price)
    assert f"{price:,.2f}" in html
    assert (
        load_workspace(
            save_workspace(edited, company["share_basis"]),
            code,
            history["end"].tolist(),
            company["share_basis"],
        )
        == edited
    )
    base = history.iloc[-1]
    assert reset_scenario(edited, company, base, "Base").scenarios == initial.scenarios
    with pytest.raises(ValueError, match="different company"):
        load_workspace(save_workspace(edited, company["share_basis"]), "4732", [], "other")
    assert (
        csv_bytes(pd.DataFrame({"Rationale": ["=SUM(1,2)"]}))
        .decode("utf-8-sig")
        .splitlines()[1]
        .startswith("\"'=")
    )
