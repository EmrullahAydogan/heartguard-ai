"""Command Center page - all 3 patients at a glance."""

import plotly.graph_objects as go
from dash import dcc, html, callback, Input, Output
import dash_bootstrap_components as dbc
from datetime import timezone

from data_client import (
    get_all_patients_latest, get_vitals_timeseries,
    get_alerts, PATIENTS
)

CATEGORY_COLOR = {
    "stable":   "#3fb950",
    "watch":    "#d29922",
    "warning":  "#f0883e",
    "critical": "#f85149",
}
CATEGORY_ICON = {
    "stable":   "bi-check-circle-fill",
    "watch":    "bi-eye-fill",
    "warning":  "bi-exclamation-triangle-fill",
    "critical": "bi-exclamation-octagon-fill",
}

GRAPH_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#8b949e", size=10),
    margin=dict(l=30, r=10, t=5, b=30),
    xaxis=dict(gridcolor="#21262d", showgrid=True, zeroline=False, showticklabels=False),
    yaxis=dict(gridcolor="#21262d", showgrid=True, zeroline=False),
    hovermode="x unified",
    showlegend=False,
)


def layout():
    return dbc.Container([
        html.Div([
            html.I(className="bi bi-grid-3x3-gap me-2", style={"color": "#58a6ff"}),
            "Command Center — All Patients",
        ], className="page-title mt-3"),

        # Patient cards row
        dbc.Row(id="cmd-patient-cards", className="g-3"),

        # Trend charts
        html.Div([
            html.I(className="bi bi-activity me-2", style={"color": "#3fb950"}),
            "Heart Rate Trends",
        ], className="hg-card-title mt-2"),
        dbc.Row(id="cmd-trend-charts", className="g-3"),

        # System alerts
        html.Div([
            html.I(className="bi bi-bell-fill me-2", style={"color": "#f0883e"}),
            "Recent Alerts — All Patients",
        ], className="hg-card-title mt-2"),
        html.Div(id="cmd-all-alerts", className="hg-card"),

        # System stats footer
        html.Div(id="cmd-stats-footer", className="hg-card mt-2"),

    ], fluid=True, style={"paddingTop": "1rem"})


@callback(
    Output("cmd-patient-cards",  "children"),
    Output("cmd-trend-charts",   "children"),
    Output("cmd-all-alerts",     "children"),
    Output("cmd-stats-footer",   "children"),
    Input("interval-fast", "n_intervals"),
)
def update_command(_):
    data = get_all_patients_latest()

    # ── Patient summary cards ──────────────────────────────────────────────
    cards = []
    for pid, info in PATIENTS.items():
        d = data.get(pid, {})
        category = d.get("risk_category", "stable")
        score = d.get("risk_score")
        color = CATEGORY_COLOR.get(category, "#3fb950")
        icon = CATEGORY_ICON.get(category, "bi-check-circle-fill")
        v = d.get("vitals", {})
        health_pct = round((1.0 - (score or 0.5)) * 100)

        card = dbc.Col(html.Div([
            # Header
            html.Div([
                html.Div([
                    html.I(className=f"bi {icon} me-2", style={"color": color}),
                    html.Span(info["name"], className="cmd-patient-name"),
                ], style={"display": "flex", "alignItems": "center"}),
                html.Div(f"{health_pct}% Health", style={
                    "color": color, "fontWeight": 700, "fontSize": "0.8rem",
                }),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "marginBottom": "0.6rem"}),
            # Category badge
            html.Div(category.upper(), style={
                "display": "inline-block",
                "background": f"{color}22",
                "border": f"1px solid {color}55",
                "color": color,
                "borderRadius": "12px",
                "padding": "2px 10px",
                "fontSize": "0.72rem",
                "fontWeight": 700,
                "marginBottom": "0.6rem",
            }),
            # Vitals grid
            html.Div([
                html.Div([
                    html.I(className="bi bi-heart-fill me-1", style={"color": "#f85149", "fontSize": "0.7rem"}),
                    "HR:", html.Span(f" {v.get('heart_rate', '—'):.0f} bpm"
                                    if v.get('heart_rate') is not None else " —")
                ], className="cmd-vital-item"),
                html.Div([
                    html.I(className="bi bi-droplet-fill me-1", style={"color": "#5794F2", "fontSize": "0.7rem"}),
                    "SpO₂:", html.Span(f" {v.get('spo2', '—'):.0f}%"
                                       if v.get('spo2') is not None else " —")
                ], className="cmd-vital-item"),
                html.Div([
                    html.I(className="bi bi-thermometer me-1", style={"color": "#FADE2A", "fontSize": "0.7rem"}),
                    "Temp:", html.Span(f" {v.get('temperature', '—'):.1f}°C"
                                       if v.get('temperature') is not None else " —")
                ], className="cmd-vital-item"),
                html.Div([
                    html.I(className="bi bi-lungs-fill me-1", style={"color": "#73BF69", "fontSize": "0.7rem"}),
                    "RR:", html.Span(f" {v.get('respiration', '—'):.0f}/min"
                                     if v.get('respiration') is not None else " —")
                ], className="cmd-vital-item"),
            ], className="cmd-vital-grid"),
        ], className=f"cmd-patient-card bg-{category}",
           style={"borderColor": f"{color}44"}),
        xs=12, md=4)

        cards.append(card)

    # ── Trend charts ─────────────────────────────────────────────────────────
    trend_cols = []
    colors_hr = ["#f85149", "#f0883e", "#bc8cff"]
    for (pid, info), col in zip(PATIENTS.items(), colors_hr):
        times, vals = get_vitals_timeseries(pid, "heart_rate")
        fig = go.Figure(go.Scatter(
            x=times, y=vals, mode="lines",
            line=dict(color=col, width=1.5),
            fill="tozeroy", fillcolor=f"rgba({','.join(str(int(col[i:i+2], 16)) for i in (1,3,5))},0.07)",
            hovertemplate="%{y:.0f} bpm<extra></extra>",
        ))
        fig.update_layout(**GRAPH_LAYOUT)
        trend_cols.append(dbc.Col(html.Div([
            html.Div(info["label"], className="hg-card-title"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "160px"}),
        ], className="hg-card"), xs=12, md=4))

    # ── All alerts ────────────────────────────────────────────────────────────
    all_alerts = []
    for pid, info in PATIENTS.items():
        for a in get_alerts(pid, limit=5):
            all_alerts.append({**a, "patient": info["label"], "pid": pid})

    all_alerts.sort(key=lambda x: x["time"] or "", reverse=True)

    if not all_alerts:
        alerts_content = html.Div("No recent alerts across all patients.", className="no-data")
    else:
        items = []
        for a in all_alerts[:15]:
            sev = a["severity"]
            color = "#f85149" if sev == "critical" else ("#f0883e" if sev == "warning" else "#58a6ff")
            icon = "bi-exclamation-octagon" if sev == "critical" else (
                "bi-exclamation-triangle" if sev == "warning" else "bi-info-circle")
            cls = f"alert-{sev}" if sev in ("critical", "warning") else "alert-info"
            t = a["time"]
            ts = t.astimezone(timezone.utc).strftime("%b %d %H:%M") if t else ""
            items.append(html.Div([
                html.I(className=f"bi {icon}", style={"color": color, "minWidth": "16px"}),
                html.Div([
                    html.Span(f"[{a['patient']}] ", style={"fontWeight": 700, "color": color}),
                    html.Span(a["message"], style={"fontSize": "0.8rem"}),
                    html.Div(ts, style={"fontSize": "0.7rem", "color": "#484f58"}),
                ]),
            ], className=f"alert-card {cls}"))
        alerts_content = html.Div(items, style={"maxHeight": "300px", "overflowY": "auto"})

    # ── Stats footer ──────────────────────────────────────────────────────────
    total_alerts = sum(len(get_alerts(pid, 100)) for pid in PATIENTS)
    critical_count = sum(
        1 for pid in PATIENTS
        for a in get_alerts(pid, 20)
        if a["severity"] == "critical"
    )
    footer = dbc.Row([
        dbc.Col(html.Div([
            html.I(className="bi bi-people-fill me-2", style={"color": "#58a6ff"}),
            html.Span("Patients Monitored: ", style={"color": "#8b949e", "fontSize": "0.82rem"}),
            html.Span(str(len(PATIENTS)), style={"fontWeight": 700, "color": "#58a6ff"}),
        ]), xs=12, sm=4),
        dbc.Col(html.Div([
            html.I(className="bi bi-bell-fill me-2", style={"color": "#f0883e"}),
            html.Span("Total Alerts: ", style={"color": "#8b949e", "fontSize": "0.82rem"}),
            html.Span(str(total_alerts), style={"fontWeight": 700, "color": "#f0883e"}),
        ]), xs=12, sm=4),
        dbc.Col(html.Div([
            html.I(className="bi bi-exclamation-octagon-fill me-2", style={"color": "#f85149"}),
            html.Span("Critical: ", style={"color": "#8b949e", "fontSize": "0.82rem"}),
            html.Span(str(critical_count), style={"fontWeight": 700, "color": "#f85149"}),
        ]), xs=12, sm=4),
    ], className="g-2 align-items-center")

    return cards, trend_cols, alerts_content, footer
