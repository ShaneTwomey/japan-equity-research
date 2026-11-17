"""Generate CSV extracts and a self-contained printable HTML report."""

from html import escape

import pandas as pd

from research.analysis import GAPS, METHOD, Analysis, historical_table, sensitivity_grid
from research.data import LABELS, Dataset
from research.model import PRICE_LABEL
from research.state import NOTES

STYLE = """
:root {color:#16283a;background:#f2f4f7;font:15px/1.55 system-ui,sans-serif}
* {box-sizing:border-box}
body {margin:0}
main {max-width:1160px;margin:28px auto;background:white;border:1px solid #d9e1e8;padding:32px}
header {border-bottom:3px solid #08776d;padding-bottom:16px;margin-bottom:22px}
h1 {font-size:30px;line-height:1.2;margin:.3em 0}
h2 {font-size:21px;margin:1.4em 0 .45em}
h3 {font-size:15px;margin:1em 0 .35em}
p, ul {margin:.4em 0 .85em}
a {color:#09645b}
.meta {color:#4b5f72}
.notice {border-left:3px solid #08776d;padding-left:10px}
.scroll {overflow:auto}
table {border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
td,th {border-bottom:1px solid #d9e1e8;padding:6px 8px;text-align:left;vertical-align:top}
td.number {text-align:right;white-space:nowrap}
th {background:#eff3f5}
.notes {white-space:pre-wrap;overflow-wrap:anywhere}
details {margin:.55em 0}
summary {cursor:pointer;font-weight:600}
@media (max-width:650px) {main {margin:0;padding:16px}}
@page {size:A4; margin:12mm;}
@media print {
    :root {font-size:10.5pt;background:white}
    main {margin:0;border:0;padding:0;max-width:none}
    .scroll {overflow:visible}
    h2,h3,summary {break-after:avoid}
    tr {break-inside:avoid}
    thead {display:table-header-group}
    table {font-size:8.5pt;table-layout:fixed}
    td,th {padding:4px 5px;overflow-wrap:anywhere}
    td.number {white-space:normal}
    th:first-child {width:24%}
    a {text-decoration:none}
}
"""


def _csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "@", "-")):
        # Preserve plain signed numeric source values and prevent spreadsheet formula execution.
        try:
            float(value.replace(",", ""))
        except ValueError:
            return "'" + value
    return value


def csv_bytes(table: pd.DataFrame) -> bytes:
    safe = table.map(_csv_cell)
    return safe.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def scenario_export(analysis: Analysis) -> pd.DataFrame:
    result = analysis.assumptions.merge(
        analysis.results.drop(columns="Assumed forward P/E (×)"), on="Scenario", validate="1:1"
    )
    reference = analysis.workspace.reference
    result.insert(0, "Securities code", analysis.workspace.company)
    return result.assign(
        **{
            "Base fiscal start": analysis.base_start,
            "Base fiscal end": analysis.base_end,
            "Forecast fiscal start": analysis.forecast_start,
            "Forecast fiscal end": analysis.forecast_end,
            "Base revenue (JPYm)": analysis.base_revenue,
            "Base revenue source ID": analysis.base_source,
            "Base revenue locator": analysis.base_locator,
            "Reference price (JPY/share)": reference.price if reference else None,
            "Reference date": reference.as_of.isoformat() if reference else None,
            "Reference source (manual)": reference.source if reference else None,
            "Share basis": analysis.share_basis,
            "Period notice": analysis.coverage_notice,
        }
    )


def _text(value) -> str:
    return escape(str(value), quote=True)


def _table(frame: pd.DataFrame, precision: int = 6, anchor_column: str | None = None) -> str:
    headers = "".join(f'<th scope="col">{_text(col)}</th>' for col in frame.columns)
    rows = []
    for row in frame.itertuples(index=False, name=None):
        cells = []
        for column, value in zip(frame.columns, row, strict=True):
            if pd.isna(value):
                cells.append('<td aria-label="Unavailable">—</td>')
            elif isinstance(value, (int, float)):
                formatted = (
                    f"{value:,.{precision}f}".rstrip("0").rstrip(".")
                    if precision
                    else f"{value:,.0f}"
                )
                cells.append(f'<td class="number">{formatted}</td>')
            elif column == anchor_column:
                cells.append(f'<td><a href="#{_text(value)}">{_text(value)}</a></td>')
            else:
                cells.append(f"<td>{_text(value)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<div class="scroll"><table><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _paragraphs(title: str, paragraphs) -> str:
    items = "".join(f"<li>{_text(item)}</li>" for item in paragraphs)
    return f"<h2>{_text(title)}</h2><ul>{items}</ul>"


def html_report(dataset: Dataset, history: pd.DataFrame, analysis: Analysis) -> bytes:
    workspace = analysis.workspace
    company = dataset.companies[workspace.company]
    facts = dataset.provenance(workspace.company)
    source_keys = list(
        dict.fromkeys(
            [
                *company["business_sources"],
                *company["context_sources"],
                *history["release"],
                *facts["source_id"],
            ]
        )
    )
    sources = []
    for key in source_keys:
        source = dataset.sources[key]
        sources.append(
            f'<li id="{_text(key)}"><strong>{_text(key)}</strong> · '
            f'<a href="{_text(source["url"])}" rel="noreferrer">{_text(source["title"])}</a> · '
            f"Published {_text(source['published'] or 'undated')} · Retrieved {_text(source['retrieved'])}. "
            f"{_text(source['locator'])} {_text(source['note'])}</li>"
        )
    business_links = ", ".join(
        f'<a href="#{_text(key)}">{_text(key)}</a>' for key in company["business_sources"]
    )
    notes = "".join(
        f'<h3>{_text(label)}</h3><p class="notes">{_text(workspace.notes[key] or "—")}</p>'
        for key, label in NOTES.items()
    )
    reference = workspace.reference
    price = (
        f"Manual reference price JPY {reference.price:,.8g} per share on {reference.as_of.isoformat()}. "
        f"Source entered by researcher: {reference.source}."
        if reference
        else "No valid manual reference price was supplied. Price upside/downside is unavailable."
    )
    # Transpose the historical body so the five annual periods print across one sheet.
    past = historical_table(history).set_index("Fiscal end").T.reset_index(names="Line item")
    history_body = _table(past)
    eps = history[
        ["end", "basic_eps", "recomputed_eps", "eps_difference", "eps_tolerance", "eps_check"]
    ]
    eps = eps.set_axis(
        [
            "Fiscal end",
            "Reported EPS (JPY)",
            "Recomputed EPS (JPY)",
            "Difference (JPY)",
            "Tolerance (JPY)",
            "Reconciliation",
        ],
        axis=1,
    )
    sens = sensitivity_grid(analysis)
    sens.columns = [f"{x:.6g}×" for x in sens.columns]
    selected = workspace.scenarios[workspace.sensitivity_case]
    annual_notes = [
        f"{row.end} [{row.release}]: {row.note}"
        for row in history.itertuples(index=False)
        if row.note
    ]
    evidence = []
    for end, records in facts.groupby("end", sort=True):
        lines = []
        for row in records.itertuples(index=False):
            treatment = row.note
            if row.source_share_basis:
                treatment = f"{row.source_share_basis} (factor {row.split_factor}). {treatment}"
            lines.append(
                (
                    LABELS[row.metric],
                    row.source_id,
                    row.locator,
                    f"{row.original_value} {row.original_unit}",
                    f"{row.normalized_value:,.9f}".rstrip("0").rstrip(".")
                    + f" {row.normalized_unit}",
                    treatment,
                )
            )
        audit = pd.DataFrame(
            lines,
            columns=["Line item", "Source", "PDF locator", "Original", "Normalized", "Treatment"],
        )
        evidence.append(
            f"<details open><summary>{_text(end)}</summary>{_table(audit, anchor_column='Source')}</details>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_text(company["short_name"])} · Japanese Equity Research</title><style>{STYLE}</style></head>
<body><main>
<header><p class="meta">Japanese Equity Research · {_text(workspace.company)} · {_text(company["industry"])}</p>
<h1>{_text(company["name"])}</h1><p class="meta">{_text(company["japanese_name"])}</p></header>
<h2>Business</h2><p>{_text(company["description"])}</p><p>Issuer sources · {business_links}</p>
<h2>Research notes</h2><p class="meta">{_text(workspace.notes_origin)}</p>{notes}
<h2>Annual financials</h2><p>Consolidated Japanese GAAP. JPYm means millions of yen. Annual release IDs refer to the source registry below.</p>
{history_body}
{_paragraphs("Period notes", annual_notes) if annual_notes else ""}
<h2>One-year scenarios</h2>
<p>Base fiscal period {_text(analysis.base_start)} through {_text(analysis.base_end)}.
Base revenue {analysis.base_revenue:,.6f} JPYm [<a href="#{_text(analysis.base_source)}">{_text(analysis.base_source)}</a>, {_text(analysis.base_locator)}].
Forecast fiscal period {_text(analysis.forecast_start)} through {_text(analysis.forecast_end)}.</p>
{f'<p class="notice">{_text(analysis.coverage_notice)}</p>' if analysis.coverage_notice else ""}
<p>Research assumptions. Case names carry no probabilities. {_text(company["share_note"])}</p>
{_table(analysis.assumptions.drop(columns="Rationale"))}
<ul>{"".join(f"<li><strong>{_text(row.Scenario)}</strong> · {_text(row.Rationale)}</li>" for row in analysis.assumptions.itertuples(index=False))}</ul>
<h3>{_text(PRICE_LABEL)}</h3>{_table(analysis.results.set_index("Scenario").T.reset_index(names="Forecast"))}
<p>{_text(price)}</p><p>Price upside/downside excludes dividends and is computed without annualization.</p>
<h2>Sensitivity · {_text(workspace.sensitivity_case)}</h2>
<p>Grid values are implied prices in JPY per share. Rows vary attributable net margin and columns vary forward P/E. Held fixed: base revenue {analysis.base_revenue:,.2f} JPYm, growth {selected.growth:.6%}, and projected weighted-average shares {selected.shares:,.6f} million.</p>
{_table(sens.reset_index())}
<h2>Basic EPS reconciliation</h2>{_table(eps)}
{_paragraphs("Methodology", METHOD)}{_paragraphs("Coverage and limitations", GAPS)}
<h2>Source registry</h2><ul>{"".join(sources)}</ul>
<h2>Line-item provenance</h2><p>Fiscal starts, reporting version and exact ends appear in the financial table. Amounts retain their source signs and units here.</p>
{"".join(evidence)}
</main></body></html>""".encode()
