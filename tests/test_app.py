from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def _switch(at, view):
    at.radio(key="view").set_value(view).run()
    assert not at.exception


def _input(at, label):
    return next(widget for widget in at.number_input if widget.label == label)


def test_company_switch_and_reset_preserve_independent_edits():
    at = AppTest.from_file(str(APP)).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    _switch(at, "Scenario lab")
    uss_growth = _input(at, "Revenue growth (%)").value
    chart_before = at.get("plotly_chart")[0].proto.spec
    _input(at, "Revenue growth (%)").set_value(17.5).run()
    assert not at.exception
    assert at.get("plotly_chart")[0].proto.spec != chart_before
    assert any("133,778.45" in node.proto.body for node in at.get("html"))
    at.selectbox(key="company").set_value("3064").run()
    assert not at.exception
    assert _input(at, "Revenue growth (%)").value == 13
    _input(at, "Revenue growth (%)").set_value(22.0).run()
    _switch(at, "Company research")
    at.text_area[0].set_value("Edited MonotaRO thesis").run()
    _switch(at, "Scenario lab")
    assert _input(at, "Revenue growth (%)").value == 22
    at.selectbox(key="company").set_value("4732").run()
    assert _input(at, "Revenue growth (%)").value == 17.5
    at.button(key="reset_4732").click().run()
    assert not at.exception
    assert _input(at, "Revenue growth (%)").value == uss_growth
    at.selectbox(key="company").set_value("3064").run()
    assert _input(at, "Revenue growth (%)").value == 22
    _switch(at, "Company research")
    assert at.text_area[0].value == "Edited MonotaRO thesis"
    _switch(at, "Sources & methodology")
    assert len(at.dataframe) == 2
    assert at.dataframe[1].value["Reconciliation"].eq("Within rounding tolerance").all()
