"""Streamlit entry point for Japanese Equity Research."""

from dataclasses import replace
from datetime import date
from html import escape

import pandas as pd
import streamlit as st

from research.analysis import COMPARABILITY, GAPS, METHOD, analyze, historical_table, tokyo_today
from research.charts import company_series, sensitivity_chart, trend
from research.data import LABELS, load_dataset, unit
from research.export import csv_bytes, html_report, scenario_export
from research.model import (
    MAX_AMOUNT,
    MIN_POSITIVE,
    PRICE_LABEL,
    SCENARIO_NAMES,
    ReferencePrice,
    compute_history,
)
from research.state import (
    NOTES,
    default_workspace,
    load_workspace,
    reset_scenario,
    save_workspace,
    usable_bases,
)

st.set_page_config(
    page_title="Japanese Equity Research", layout="wide", initial_sidebar_state="auto"
)

SHELL_STYLE = """
<style>
.stApp {font-variant-numeric: tabular-nums;}
[data-testid="stMainBlockContainer"] {max-width: 1420px; padding-top: 3.1rem; padding-bottom: 2rem;}
[data-testid="stSidebar"] {border-right: 1px solid #dce4ea;}
[data-testid="stSidebarContent"] {background: #f2f4f7;}
[data-testid="stSidebarUserContent"] {padding-top: 2rem;}
[data-testid="stHeadingWithActionElements"] h1 {font-size: 1.84rem; line-height: 1.2; letter-spacing: -.025em;}
[data-testid="stHeadingWithActionElements"] h2 {font-size: 1.27rem; letter-spacing: -.01em;}
[data-testid="stHeadingWithActionElements"] h3 {font-size: 1.04rem;}
[data-testid="stPlotlyChart"] {border: 1px solid #dce4ea; border-radius: 8px; overflow: hidden;}
[data-testid="stWidgetLabel"] p {font-size: .92rem;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color: #4f6171; opacity: 1;}
.ledger-wrap {overflow-x: auto; border: 1px solid #dce4ea; border-radius: 8px; background: white;}
.ledger {border-collapse: collapse; width: 100%; font-size: .86rem; line-height: 1.25;}
.ledger th, .ledger td {padding: .58rem .67rem; border-bottom: 1px solid #e5ebf0; vertical-align: middle;}
.ledger th {text-align: left; font-weight: 550; color: #384e63;}
.ledger thead th:not(:first-child), .ledger td {text-align: right;}
.ledger thead th {white-space: nowrap;}
.ledger tbody tr:last-child > * {border-bottom: 0;}
.ledger td {white-space: nowrap; color: #16283a;}
.ledger abbr {text-decoration: none;}
.brand {display: flex; gap: .75rem; align-items: center; font-size: 1rem; font-weight: 650; line-height: 1.15;}
.brand-mark {width: 27px; height: 23px; border-left: 2px solid #08776d; border-bottom: 2px solid #08776d;
  background: repeating-linear-gradient(to bottom, transparent 0 5px, #dce7e6 5px 6px); position: relative; flex: none;}
.brand-mark::after {content: ""; height: 2px; background: #08776d; position: absolute; left: 3px; right: 0;
  top: 8px; transform: rotate(-28deg);}
@media (max-width: 1120px) {
  [data-testid="stMainBlockContainer"] {padding-inline: 2rem;}
}
@media (max-width: 980px) {
  .st-key-overview_panels [data-testid="stHorizontalBlock"] {flex-direction: column;}
  .st-key-overview_panels [data-testid="stColumn"] {width: 100%; flex: auto;}
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] {padding: 3rem 1rem 2rem;}
  [data-testid="stHeadingWithActionElements"] h1 {font-size: 1.45rem;}
  .ledger th, .ledger td {padding: .48rem .45rem;}
  .ledger {font-size: .8rem;}
}
</style>
"""

COMPARE = {
    "Revenue growth": "revenue_growth",
    "Operating margin": "operating_margin",
    "Attributable net margin": "net_margin",
    "Cash flow after capital expenditure": "cash_after_capex",
}
PLOT_CONFIG = {"displayModeBar": False, "responsive": True}
VIEWS = ("Overview", "Company research", "Scenario lab", "Sources & methodology")


@st.cache_data(show_spinner=False)
def bundled():
    dataset = load_dataset()
    histories = {code: compute_history(dataset, code) for code in dataset.companies}
    return dataset, histories


def current(code):
    return st.session_state.books[code]


def update(workspace):
    st.session_state.books[workspace.company] = workspace


def seed_widget(key, value):
    if key not in st.session_state:
        st.session_state[key] = value


def table(frame, *, height="auto", pinned=None):
    config = {}
    for name in frame.select_dtypes(include="number").columns:
        value_format = "localized"
        if "(%)" in name:
            value_format = (
                "%+.2f%%" if name.startswith(("Revenue growth", "Price upside")) else "%.2f%%"
            )
        elif "(×)" in name:
            value_format = "%.2f×"
        config[name] = st.column_config.NumberColumn(format=value_format)
    if pinned:
        config[pinned] = st.column_config.TextColumn(pinned, pinned=True)
    st.dataframe(frame, hide_index=True, width="stretch", height=height, column_config=config)


def show_plot(figure, key):
    st.plotly_chart(figure, theme=None, width="stretch", config=PLOT_CONFIG, key=key)


def ledger(headings, rows):
    header = "".join(f'<th scope="col">{escape(title)}</th>' for title in headings)
    body = []
    for label, *values in rows:
        cells = "".join(
            f"<td>{escape(value)}</td>"
            if value is not None
            else '<td><abbr title="Unavailable">—</abbr></td>'
            for value in values
        )
        body.append(f'<tr><th scope="row">{escape(label)}</th>{cells}</tr>')
    st.html(
        f'<div class="ledger-wrap"><table class="ledger"><thead><tr>{header}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def number(value, precision=2, suffix="", signed=False):
    if pd.isna(value):
        return None
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:,.{precision}f}{suffix}"


def heading(title, subtitle):
    st.title(title, anchor=False)
    st.caption(subtitle)


def download(label, content, code, suffix, mime, **kwargs):
    st.download_button(
        label, content, file_name=f"{code}-{suffix}", mime=mime, on_click="ignore", **kwargs
    )


def overview(dataset, histories):
    heading(
        "Japanese Equity Research", "Issuer-reported annual financials · Consolidated Japanese GAAP"
    )
    rows = []
    for code, history in histories.items():
        latest = history.iloc[-1]
        rows.append(
            {
                "Company": f"{dataset.companies[code]['short_name']} · {code}",
                "Fiscal end": latest["end"],
                "Annual periods": len(history),
                "Revenue (JPYm)": latest["revenue"],
                "Revenue growth (%)": 100 * latest["revenue_growth"],
                "Operating margin (%)": 100 * latest["operating_margin"],
                "Attributable net margin (%)": 100 * latest["net_margin"],
                "Operating cash flow (JPYm)": latest["operating_cash_flow"],
                "Cash flow after capital expenditure (JPYm)": latest["cash_after_capex"],
                "Annual release ID": latest["release"],
            }
        )
    left, right = st.container(key="overview_panels").columns([1, 1.15], gap="medium")
    with left:
        st.subheader("Latest annual results", anchor=False)
        st.caption("Amounts in millions of yen")
        lines = [("Fiscal year end", *(row["Fiscal end"] for row in rows))]
        for field, label, digits, suffix, signed in (
            ("Annual periods", "Annual periods", 0, "", False),
            ("Revenue (JPYm)", "Revenue", 0, "", False),
            ("Revenue growth (%)", "Revenue growth", 2, "%", True),
            ("Operating margin (%)", "Operating margin", 2, "%", False),
            ("Attributable net margin (%)", "Attributable net margin", 2, "%", False),
            ("Operating cash flow (JPYm)", "Operating cash flow", 0, "", False),
            (
                "Cash flow after capital expenditure (JPYm)",
                "Cash flow after capital expenditure",
                0,
                "",
                False,
            ),
        ):
            lines.append((label, *(number(row[field], digits, suffix, signed) for row in rows)))
        lines.append(("Annual release ID", *(row["Annual release ID"] for row in rows)))
        ledger(("Metric", *(row["Company"] for row in rows)), lines)
    with right:
        st.subheader("Compare annual trends", anchor=False)
        choice = st.selectbox("Comparison metric", list(COMPARE), index=1)
        series = [
            (dataset.companies[code]["short_name"], history, COMPARE[choice])
            for code, history in histories.items()
        ]
        show_plot(trend(series, height=280), "comparison-chart")
    st.caption(COMPARABILITY)
    download(
        "Download comparison CSV",
        csv_bytes(pd.DataFrame(rows)),
        "japan",
        "comparison.csv",
        "text/csv",
    )


def source_line(dataset, source_id):
    source = dataset.sources[source_id]
    st.markdown(f"**{source_id}** · [{source['title']}]({source['url']})")
    date_info = f"Published {source['published'] or 'undated'} · Retrieved {source['retrieved']}"
    details = " ".join(part for part in (source["locator"], source["note"]) if part)
    st.caption(f"{date_info} · {details}")


def audit(dataset, code, history, key):
    year = st.selectbox(
        "Fiscal year end to inspect", history["end"].tolist()[::-1], key=f"audit_{key}"
    )
    subset = dataset.provenance(code)
    subset = subset.loc[subset["end"].eq(year)]
    row = history.loc[history["end"].eq(year)].iloc[0]
    st.caption(
        f"{row['start']} → {row['end']} · {row['reporting']} {row['accounting']} · {row['version']}"
    )
    if row["note"]:
        st.caption(row["note"])
    for source_id in dict.fromkeys([row["release"], *subset["source_id"]]):
        source_line(dataset, source_id)
    table(
        subset.assign(metric=subset["metric"].map(LABELS))[
            [
                "metric",
                "original_value",
                "original_unit",
                "normalized_value",
                "normalized_unit",
                "source_id",
                "locator",
                "source_share_basis",
                "split_factor",
                "note",
            ]
        ].set_axis(
            [
                "Line item",
                "Original value",
                "Original unit",
                "Normalized value",
                "Normalized unit",
                "Source ID",
                "Page and line",
                "Reported share basis",
                "Split factor",
                "Normalization",
            ],
            axis=1,
        ),
        height=380,
        pinned="Line item",
    )
    download(
        "Download all line-item provenance CSV",
        csv_bytes(dataset.provenance(code)),
        code,
        f"{key}-provenance.csv",
        "text/csv",
        key=f"provenance_{key}",
    )


def history_and_notes(dataset, code, history):
    company = dataset.companies[code]
    heading(company["name"], f"{code} · {company['japanese_name']} · {company['industry']}")
    st.write(company["description"])
    with st.expander("Business sources"):
        for source_id in company["business_sources"]:
            source_line(dataset, source_id)

    st.subheader("Annual financials", anchor=False)
    st.caption(
        f"{len(history)} annual periods · {history.iloc[0]['start']} through {history.iloc[-1]['end']} "
        "· Consolidated Japanese GAAP. Blank cells indicate unavailable values."
    )
    table(historical_table(history), height=218, pinned="Fiscal start")
    download(
        "Download historical financials CSV",
        csv_bytes(historical_table(history)),
        code,
        "annual-financials.csv",
        "text/csv",
    )
    with st.expander("Inspect reported figures and source pages"):
        audit(dataset, code, history, "company")
    st.subheader("Financial trends", anchor=False)
    views = {
        "Revenue and profit": ("revenue", "operating_profit", "attributable_profit"),
        "Margins": ("operating_margin", "net_margin"),
        "Cash flow": ("operating_cash_flow", "cash_capex", "cash_after_capex"),
    }
    selected = st.radio(
        "Financial trend", list(views), horizontal=True, label_visibility="collapsed"
    )
    show_plot(trend(company_series(history, views[selected])), "company-trend")

    st.subheader("Research notes", anchor=False)
    if code not in st.session_state.books:
        st.info("Research notes are unavailable until the dataset includes an eligible base year.")
        return
    st.caption(
        f"{current(code).notes_origin} · Edits stay with this company. Save them through Scenario lab."
    )
    revision = st.session_state.revisions[code]
    narrative = current(code)
    for key, label in NOTES.items():
        widget = f"note_{code}_{revision}_{key}"
        seed_widget(widget, narrative.notes[key])
        st.text_area(
            label,
            key=widget,
            height=100,
            max_chars=3500,
            on_change=edit_note,
            args=(code, key, widget),
        )


def edit_note(code, key, widget):
    state = current(code)
    update(
        replace(
            state,
            notes={**state.notes, key: st.session_state[widget]},
            notes_origin="Edited research notes",
        )
    )


def change_base(code, widget):
    update(replace(current(code), base_end=st.session_state[widget]))


def select_case(code, widget):
    case = st.session_state[widget]
    if case in SCENARIO_NAMES:
        update(replace(current(code), sensitivity_case=case))


def edit_scenario(code, case, field, widget, scale=1):
    workspace = current(code)
    value = st.session_state[widget]
    if scale != 1:
        value /= scale
    scenario = replace(workspace.scenarios[case], **{field: value})
    update(replace(workspace, scenarios={**workspace.scenarios, case: scenario}))


def do_reset(code, company, base, case):
    update(reset_scenario(current(code), company, base, case))
    st.session_state.revisions[code] += 1


def _reference_values(reference):
    return {
        "price": reference.price if reference else None,
        "as_of": reference.as_of if reference else None,
        "source": reference.source if reference else "",
        "confirmed": reference is not None,
    }


def change_reference(code, basis, field, widget):
    drafts = st.session_state.reference_drafts
    values = drafts.setdefault(code, _reference_values(current(code).reference))
    values[field] = st.session_state[widget]
    ref = None
    if all((values["price"], values["as_of"], values["source"].strip(), values["confirmed"])):
        if values["as_of"] <= tokyo_today():
            ref = ReferencePrice(values["price"], values["as_of"], values["source"].strip(), basis)
    update(replace(current(code), reference=ref))


def reference_editor(code, basis, revision):
    state = current(code)
    values = st.session_state.reference_drafts.get(code, _reference_values(state.reference))
    with st.expander("Manual reference share price"):
        st.caption("Enter a JPY closing or reference price, its as-of date and your source.")
        price, as_of = st.columns(2)
        controls = {
            "price": (
                price.number_input,
                "Reference price (JPY/share)",
                dict(min_value=MIN_POSITIVE, max_value=MAX_AMOUNT, step=1.0, format="%.6f"),
            ),
            "as_of": (
                as_of.date_input,
                "Reference date",
                dict(min_value=date(1900, 1, 1), max_value=tokyo_today(), format="YYYY-MM-DD"),
            ),
            "source": (st.text_input, "Reference source", dict(max_chars=300)),
            "confirmed": (st.checkbox, f"Price uses the same basis as forecast EPS · {basis}", {}),
        }
        for field, (render, label, options) in controls.items():
            widget = f"ref_{code}_{revision}_{field}"
            seed_widget(widget, values[field])
            if field == "as_of":
                options["value"] = None
            elif field == "price":
                options["value"] = None
            render(
                label,
                key=widget,
                on_change=change_reference,
                args=(code, basis, field, widget),
                **options,
            )
        if state.reference:
            st.caption(
                f"Manual input · JPY {state.reference.price:,.2f} · "
                f"{state.reference.as_of.isoformat()} · {state.reference.source}"
            )
        elif any(values.values()):
            st.warning(
                "Provide a positive price, date, source and share-basis confirmation to calculate price upside/downside."
            )
        else:
            st.caption("Price upside/downside is unavailable until a reference is supplied.")


def load_uploaded(code, allowed_ends, basis, upload_key):
    uploaded = st.session_state[upload_key]
    if uploaded is None:
        st.session_state.import_status[code] = ("warning", "Choose a JSON research file first.")
        return
    try:
        imported = load_workspace(uploaded.getvalue(), code, allowed_ends, basis)
        if imported.reference and imported.reference.as_of > tokyo_today():
            raise ValueError("The reference date in this research file is in the future.")
    except ValueError as exc:
        st.session_state.import_status[code] = ("error", str(exc))
    else:
        update(imported)
        st.session_state.reference_drafts.pop(code, None)
        st.session_state.revisions[code] += 1
        st.session_state.import_status[code] = ("success", "Research file loaded.")


def forecast_ledger(results):
    formats = (
        ("Forecast revenue (JPYm)", "Revenue", 2, "", False),
        ("Forecast attributable profit (JPYm)", "Attributable profit", 2, "", False),
        ("Forecast basic EPS (JPY/share)", "Basic EPS", 2, "", False),
        ("Assumed forward P/E (×)", "Forward P/E", 2, "×", False),
        ("Implied price (JPY/share)", "Implied price", 2, "", False),
        ("Price upside/downside (%)", "Price upside/downside", 2, "%", True),
    )
    lines = [
        (label, *(number(value, digits, suffix, signed) for value in results[field]))
        for field, label, digits, suffix, signed in formats
    ]
    ledger(("Forecast", *results["Scenario"]), lines)
    if results["Implied price (JPY/share)"].isna().any():
        st.caption("P/E valuation is unavailable for any case with zero or negative forecast EPS.")


def scenario_lab(dataset, code, history):
    company = dataset.companies[code]
    basis = company["share_basis"]
    heading(
        "Scenario lab", f"{company['name']} · {code} · One-year earnings and implied share price"
    )
    eligible = usable_bases(history)
    if eligible.empty:
        st.info("Scenario modelling needs annual revenue and verified weighted-average shares.")
        return
    state = current(code)
    revision = st.session_state.revisions[code]
    dates = eligible["end"].tolist()[::-1]
    base_key = f"base_{code}_{revision}"
    seed_widget(base_key, state.base_end)
    st.selectbox(
        "Historical base fiscal year end",
        dates,
        key=base_key,
        on_change=change_base,
        args=(code, base_key),
        width=350,
    )
    base = eligible.loc[eligible["end"].eq(state.base_end)].iloc[0]
    analysis = analyze(dataset, history, state)
    st.markdown(
        f"**Base** {analysis.base_start} → {analysis.base_end}  ·  "
        f"**Forecast** {analysis.forecast_start} → {analysis.forecast_end}"
    )
    base_source = dataset.sources[analysis.base_source]
    st.caption(
        f"Base revenue {analysis.base_revenue:,.2f} JPYm · "
        f"[{analysis.base_source}]({base_source['url']}) · {analysis.base_locator}"
    )
    if analysis.coverage_notice:
        st.warning(analysis.coverage_notice)
    st.subheader("Scenario assumptions", anchor=False)
    st.caption(
        "Defaults are illustrative. Bear, Base, and Bull carry no assigned probabilities. "
        f"Projected weighted-average shares use {basis}. Switching the base preserves edits."
    )
    case_key = f"case_{code}_{revision}"
    seed_widget(case_key, state.sensitivity_case)
    st.radio(
        "Scenario to edit and test",
        SCENARIO_NAMES,
        key=case_key,
        horizontal=True,
        on_change=select_case,
        args=(code, case_key),
    )
    case = state.sensitivity_case
    assumption = state.scenarios[case]
    cols = st.columns(4)
    controls = (
        (
            "growth",
            "Revenue growth (%)",
            100,
            -100.0,
            10000.0,
            0.5,
            "%.4f",
            "Applied to the selected year’s reported revenue.",
        ),
        (
            "margin",
            "Attributable net margin (%)",
            100,
            -10000.0,
            10000.0,
            0.5,
            "%.4f",
            "Forecast profit attributable to owners of the parent divided by revenue.",
        ),
        (
            "shares",
            "Weighted-average shares (m)",
            1,
            MIN_POSITIVE,
            MAX_AMOUNT,
            1.0,
            "%.6f",
            "Projected ordinary shares on the model’s documented split basis.",
        ),
        (
            "pe",
            "Forward P/E (×)",
            1,
            MIN_POSITIVE,
            MAX_AMOUNT,
            0.5,
            "%.4f",
            "Assumed multiple of positive forecast basic EPS.",
        ),
    )
    for col, (field, label, scale, low, high, step, fmt, help_text) in zip(
        cols, controls, strict=True
    ):
        widget = f"scenario_{code}_{revision}_{case}_{field}"
        seed_widget(widget, float(getattr(assumption, field) * scale))
        col.number_input(
            label,
            min_value=low,
            max_value=high,
            step=step,
            format=fmt,
            key=widget,
            help=help_text,
            on_change=edit_scenario,
            args=(code, case, field, widget, scale),
        )
    rationale_key = f"scenario_{code}_{revision}_{case}_rationale"
    seed_widget(rationale_key, assumption.rationale)
    st.text_area(
        "Assumption rationale",
        key=rationale_key,
        height=88,
        max_chars=1600,
        on_change=edit_scenario,
        args=(code, case, "rationale", rationale_key),
    )
    st.button(
        "Reset selected scenario",
        key=f"reset_{code}",
        on_click=do_reset,
        args=(code, company, base, case),
        help="Restore this case’s defaults using the selected base’s shares.",
    )

    st.subheader("Forecast and valuation", anchor=False)
    st.markdown(f"**{PRICE_LABEL}**")
    st.caption("Revenue and profit in JPY millions · EPS and implied price in JPY/share")
    forecast_ledger(analysis.results)
    if state.reference:
        st.caption(
            f"Manual comparison price: JPY {state.reference.price:,.2f} on "
            f"{state.reference.as_of.isoformat()} · {state.reference.source}"
        )
    st.caption("Price upside/downside excludes dividends and is shown without annualization.")
    reference_editor(code, basis, revision)
    with st.expander("Compare assumptions across cases"):
        table(analysis.assumptions, pinned="Scenario")
    st.subheader(f"Sensitivity · {case}", anchor=False)
    st.caption(
        f"Cell values are implied JPY/share. Held fixed for {analysis.forecast_end}: "
        f"{analysis.base_revenue:,.2f} JPYm base revenue, {assumption.growth:.4%} growth and "
        f"{assumption.shares:,.6f} million weighted-average shares. An em dash marks unavailable P/E valuation."
    )
    show_plot(sensitivity_chart(analysis), "valuation-heatmap")

    st.subheader("Save, load and export", anchor=False)
    st.caption("Downloads include the current company’s scenario assumptions and research notes.")
    primary, secondary = st.columns(2)
    with primary:
        download(
            "Download research report",
            html_report(dataset, history, analysis),
            code,
            "research-report.html",
            "text/html",
            type="primary",
        )
    with secondary:
        download(
            "Save research JSON",
            save_workspace(state, basis),
            code,
            "research.json",
            "application/json",
        )
    with st.expander("CSV exports and load research JSON"):
        download(
            "Download scenario CSV",
            csv_bytes(scenario_export(analysis)),
            code,
            "scenarios.csv",
            "text/csv",
        )
        download(
            "Download sensitivity CSV",
            csv_bytes(analysis.sensitivity),
            code,
            "sensitivity.csv",
            "text/csv",
        )
        upload_key = f"upload_{code}_{revision}"
        st.file_uploader("Research JSON for this company", type=["json"], key=upload_key)
        st.button(
            "Load research JSON",
            on_click=load_uploaded,
            args=(code, dates, basis, upload_key),
            key=f"load_{code}",
        )
        if status := st.session_state.import_status.get(code):
            getattr(st, status[0])(status[1])


def methodology(dataset, code, history):
    company = dataset.companies[code]
    heading(
        "Sources & methodology",
        f"{company['name']} · {code} · Annual source register and model conventions",
    )
    st.subheader("Fiscal period and provenance", anchor=False)
    audit(dataset, code, history, "method")
    with st.expander("Company source registry"):
        for source_id, source in dataset.sources.items():
            if source["code"] == code:
                source_line(dataset, source_id)
    st.subheader("Share basis and EPS reconciliation", anchor=False)
    st.write(company["share_note"])
    st.caption(
        "EPS uses profit attributable to owners of the parent and weighted-average ordinary shares. "
        "The check allows JPY 0.005 rounding plus JPY 1 million ÷ the weighted-average share count."
    )
    fields = ["end", "basic_eps", "recomputed_eps", "eps_difference", "eps_tolerance", "eps_check"]
    table(
        history[fields].set_axis(
            [
                "Fiscal end",
                f"Reported EPS ({unit('basic_eps')})",
                "Recomputed EPS (JPY/share)",
                "Difference (JPY/share)",
                "Tolerance (JPY/share)",
                "Reconciliation",
            ],
            axis=1,
        ),
        pinned="Fiscal end",
    )
    st.subheader("Calculation conventions", anchor=False)
    for item in METHOD:
        st.markdown(f"- {item}")
    st.subheader("Coverage notes", anchor=False)
    st.caption(
        "Reported amounts and same-basis reported EPS originate in issuer documents. "
        "Ratios and forecasts are calculated. Guidance is outside this dataset."
    )
    for item in GAPS:
        st.markdown(f"- {item}")
    st.caption("Dataset maintenance steps are in docs/data-update.md in the repository.")


def main():
    st.html(SHELL_STYLE)
    try:
        dataset, histories = bundled()
    except (ValueError, OSError) as exc:
        st.error(f"Bundled data could not be validated. {exc}")
        st.stop()
    if "books" not in st.session_state:
        st.session_state.books = {
            code: default_workspace(code, dataset.companies[code], history)
            for code, history in histories.items()
            if not usable_bases(history).empty
        }
        st.session_state.revisions = dict.fromkeys(histories, 0)
        st.session_state.reference_drafts = {}
        st.session_state.import_status = {}
    with st.sidebar:
        st.html(
            '<div class="brand"><span class="brand-mark" aria-hidden="true"></span>'
            "<span>Japanese Equity<br>Research</span></div>"
        )
        st.divider()
        view = st.radio("View", VIEWS, key="view", label_visibility="collapsed")
        code = st.selectbox(
            "Company",
            list(dataset.companies),
            key="company",
            format_func=lambda c: f"{dataset.companies[c]['short_name']} · {c}",
        )
        st.caption("Annual statements · Source-linked inputs")
    history = histories[code]
    if view == "Overview":
        overview(dataset, histories)
    elif view == "Company research":
        history_and_notes(dataset, code, history)
    elif view == "Scenario lab":
        scenario_lab(dataset, code, history)
    else:
        methodology(dataset, code, history)


if __name__ == "__main__":
    main()
