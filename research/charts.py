"""Plotly charts with units, exact-date hover labels, and consistent scales."""

import pandas as pd
import plotly.graph_objects as go

from research.analysis import Analysis, sensitivity_grid
from research.data import LABELS, unit

COLORS = ("#08776d", "#28465f", "#728398")


def _layout(figure: go.Figure, height: int, *, legend=True) -> go.Figure:
    figure.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=44, r=15, t=35, b=48),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#24384b", size=12),
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom"),
        showlegend=legend,
        hovermode="closest",
    )
    figure.update_xaxes(showgrid=False, showline=True, linecolor="#d9e2e9", automargin=True)
    figure.update_yaxes(gridcolor="#e9eef2", zerolinecolor="#c5d1da", automargin=True, nticks=6)
    return figure


def trend(series: list[tuple[str, pd.DataFrame, str]], height: int = 310) -> go.Figure:
    figure = go.Figure()
    axis_unit = unit(series[0][2])
    percent = axis_unit == "%"
    for index, (label, history, field) in enumerate(series):
        y = history[field] * (100 if percent else 1)
        figure.add_scatter(
            x=history["end"],
            y=y,
            name=label,
            mode="lines+markers",
            connectgaps=False,
            line=dict(color=COLORS[index], width=2.7, dash="solid" if index != 1 else "dash"),
            marker=dict(size=6, symbol=("circle", "diamond", "square")[index]),
            hovertemplate=f"Fiscal end %{{x|%Y-%m-%d}}<br>{label} %{{y:,.2f}} {axis_unit}<extra></extra>",
        )
    _layout(figure, height, legend=len(series) > 1)
    figure.update_xaxes(type="date", title="Fiscal year end", tickformat="%Y-%m", nticks=5)
    figure.update_yaxes(title=axis_unit, tickformat=",.0f", ticksuffix="%" if percent else "")
    return figure


def sensitivity_chart(analysis: Analysis) -> go.Figure:
    grid = sensitivity_grid(analysis)
    multiples = [f"{value:.6g}×" for value in grid.columns]
    margins = [f"{value:.6g}%" for value in grid.index]
    rows = grid.to_numpy().tolist()
    colors = [[None if pd.isna(value) else value for value in row] for row in rows]
    visible = [["—" if value is None else f"{value:,.0f}" for value in row] for row in colors]
    figure = go.Figure(
        go.Heatmap(
            x=multiples,
            y=margins,
            z=colors,
            colorscale=[[0, "#eaf4f1"], [0.65, "#85bab2"], [1, "#49918a"]],
            text=visible,
            texttemplate="%{text}",
            textfont={"color": "#071c21", "size": 13},
            xgap=2,
            ygap=2,
            showscale=False,
            hoverongaps=False,
            hovertemplate="Margin %{y}<br>Forward P/E %{x}<br>JPY %{z:,.2f}<extra></extra>",
        )
    )
    for row, margin in enumerate(margins):
        for col, multiple in enumerate(multiples):
            if colors[row][col] is None:
                figure.add_annotation(x=multiple, y=margin, text="—", showarrow=False)
    _layout(figure, 315, legend=False)
    figure.update_xaxes(title="Forward P/E (×)", type="category", showline=False)
    figure.update_yaxes(title="Attributable net margin (%)", showgrid=False, type="category")
    return figure


def company_series(history: pd.DataFrame, fields: tuple[str, ...]):
    return [(LABELS[field].split(",")[0], history, field) for field in fields]
