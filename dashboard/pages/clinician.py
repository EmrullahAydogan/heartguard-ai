"""Clinician Dashboard page."""

import plotly.graph_objects as go
from dash import dcc, html, callback, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import timezone

from data_client import (
    get_vitals_timeseries, get_latest_vitals, get_risk_score,
    get_medgemma_assessment, get_alerts, get_clinician_report,
    get_nyha_class, PATIENTS
)

GRAPH_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#8b949e", size=11),
    margin=dict(l=40, r=10, t=10, b=40),
    xaxis=dict(gridcolor="#21262d", showgrid=True, zeroline=False),
    yaxis=dict(gridcolor="#21262d", showgrid=True, zeroline=False),
    hovermode="x unified",
)

CATEGORY_COLOR = {
    "stable":   "#3fb950",
    "watch":    "#d29922",
    "warning":  "#f0883e",
    "critical": "#f85149",
}

def layout():
    return dbc.Container([
        dcc.Store(id="clin-patient", data="341781"),
        html.Div([
            html.I(className="bi bi-clipboard2-pulse me-2", style={"color": "#bc8cff"}),
            "Clinician Dashboard",
        ], className="page-title mt-3"),
        # Patient selector
        html.Div([
            html.Div("Select Patient", className="hg-card-title mb-2"),
            html.Div(id="clin-pills"),
        ], className="hg-card"),
        # Top row: Risk + NYHA + Vitals
        dbc.Row([
            dbc.Col(html.Div(id="clin-risk-card"), xs=12, md=4),
            dbc.Col(html.Div(id="clin-nyha-card"), xs=12, md=4),
            dbc.Col(html.Div(id="clin-flags-card"), xs=12, md=4),
        ], className="g-3"),
        # Charts
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div("Heart Rate", className="hg-card-title"),
                    dcc.Graph(id="clin-chart-hr", config={"displayModeBar": False},
                              style={"height": "200px"}),
                ], className="hg-card"),
            ], xs=12, lg=6),
            dbc.Col([
                html.Div([
                    html.Div("SpO₂ / Temperature / Respiration", className="hg-card-title"),
                    dcc.Graph(id="clin-chart-multi", config={"displayModeBar": False},
                              style={"height": "200px"}),
                ], className="hg-card"),
            ], xs=12, lg=6),
        ], className="g-3"),
        # MedGemma Assessment
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.I(className="bi bi-robot me-2", style={"color": "#bc8cff"}),
                        "MedGemma AI Assessment",
                    ], className="hg-card-title"),
                    html.Div(id="clin-assessment"),
                ], className="hg-card"),
            ], xs=12, lg=7),
            dbc.Col([
                html.Div([
                    html.Div([
                        html.I(className="bi bi-bell me-2", style={"color": "#f0883e"}),
                        "Active Alerts",
                    ], className="hg-card-title"),
                    html.Div(id="clin-alerts"),
                ], className="hg-card"),
            ], xs=12, lg=5),
        ], className="g-3"),
        # SOAP Report
        html.Div([
            html.Div([
                html.I(className="bi bi-file-medical me-2", style={"color": "#58a6ff"}),
                "Latest Clinician Report (SOAP)",
            ], className="hg-card-title"),
            html.Div(id="clin-soap"),
        ], className="hg-card"),
    ], fluid=True, style={"paddingTop": "1rem"})


# ── Callbacks ────────────────────────────────────────────────────────────────

@callback(Output("clin-pills", "children"), Input("clin-patient", "data"))
def clin_render_pills(selected):
    pills = []
    for pid, info in PATIENTS.items():
        cls = "patient-pill selected" if pid == selected else "patient-pill"
        pills.append(
            html.Span(info["label"] + f" — {info['type']}",
                      className=cls, id={"type": "clin-pill", "pid": pid})
        )
    return pills


@callback(
    Output("clin-patient", "data"),
    Input({"type": "clin-pill", "pid": "341781"}, "n_clicks"),
    Input({"type": "clin-pill", "pid": "447543"}, "n_clicks"),
    Input({"type": "clin-pill", "pid": "3141080"}, "n_clicks"),
    State("clin-patient", "data"),
    prevent_initial_call=True,
)
def clin_select(c1, c2, c3, current):
    from dash import ctx
    if not ctx.triggered_id:
        return current
    return ctx.triggered_id["pid"]


@callback(
    Output("clin-risk-card",    "children"),
    Output("clin-nyha-card",    "children"),
    Output("clin-flags-card",   "children"),
    Output("clin-chart-hr",     "figure"),
    Output("clin-chart-multi",  "figure"),
    Output("clin-assessment",   "children"),
    Output("clin-alerts",       "children"),
    Output("clin-soap",         "children"),
    Input("interval-fast", "n_intervals"),
    Input("interval-slow", "n_intervals"),
    Input("clin-patient", "data"),
)
def update_clinician(_, _2, patient_id):
    score, category = get_risk_score(patient_id)
    category = category or "stable"
    color = CATEGORY_COLOR.get(category, "#3fb950")
    health_pct = round((1.0 - (score or 0.5)) * 100)

    # Risk card
    risk_card = html.Div([
        html.Div("Risk Score", className="hg-card-title"),
        html.Div([
            html.Span(f"{health_pct}%", className="stat-value", style={"color": color}),
        ]),
        html.Div(category.upper(), style={"color": color, "fontWeight": 700,
                                          "fontSize": "0.8rem", "marginTop": "4px"}),
        dcc.Graph(
            figure=go.Figure(go.Indicator(
                mode="gauge",
                value=health_pct,
                gauge=dict(
                    axis=dict(range=[0, 100], tickcolor="#484f58"),
                    bar=dict(color=color, thickness=0.25),
                    bgcolor="rgba(0,0,0,0)",
                    bordercolor="#30363d",
                    steps=[
                        dict(range=[0, 20],  color="rgba(248,81,73,0.13)"),
                        dict(range=[20, 40], color="rgba(240,136,62,0.13)"),
                        dict(range=[40, 70], color="rgba(210,153,34,0.13)"),
                        dict(range=[70, 100],color="rgba(63,185,80,0.13)"),
                    ],
                ),
            )).update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8b949e"),
                margin=dict(l=20, r=20, t=20, b=20),
                height=120,
            ),
            config={"displayModeBar": False},
            style={"height": "120px"},
        ),
    ], className="hg-card")

    # NYHA card
    nyha = get_nyha_class(patient_id)
    nyha_card = html.Div([
        html.Div("NYHA Class", className="hg-card-title"),
        html.Div(
            f"Class {nyha}" if nyha else "—",
            className="stat-value", style={"color": "#bc8cff", "fontSize": "2.8rem"},
        ),
        html.Div("Heart Failure Classification", className="stat-label"),
    ], className="hg-card", style={"height": "100%"})

    # Flags card
    assessment = get_medgemma_assessment(patient_id)
    concerns_raw = assessment.get("key_concerns", "")
    concerns_list = [f.strip() for f in concerns_raw.split(".") if f.strip()] if concerns_raw else []
    flags_card = html.Div([
        html.Div("Key Concerns", className="hg-card-title"),
        html.Div(
            [html.Div([html.I(className="bi bi-exclamation-circle me-2",
                              style={"color": "#f0883e"}), f],
                      style={"fontSize": "0.82rem", "marginBottom": "4px"})
             for f in concerns_list]
            if concerns_list else html.Div("No active concerns", className="no-data"),
        ),
    ], className="hg-card", style={"height": "100%"})

    # HR chart
    times_hr, vals_hr = get_vitals_timeseries(patient_id, "heart_rate")
    fig_hr = go.Figure(go.Scatter(
        x=times_hr, y=vals_hr, mode="lines",
        line=dict(color="#f85149", width=1.5),
        fill="tozeroy", fillcolor="rgba(248,81,73,0.07)",
        hovertemplate="%{y:.0f} bpm<extra></extra>",
    ))
    fig_hr.update_layout(**GRAPH_LAYOUT)

    # Multi chart
    times_sp, vals_sp = get_vitals_timeseries(patient_id, "spo2")
    times_rr, vals_rr = get_vitals_timeseries(patient_id, "respiration")
    fig_multi = go.Figure()
    fig_multi.add_trace(go.Scatter(x=times_sp, y=vals_sp, name="SpO₂",
                                   line=dict(color="#5794F2", width=1.5),
                                   hovertemplate="%{y:.0f}%<extra>SpO₂</extra>"))
    fig_multi.add_trace(go.Scatter(x=times_rr, y=vals_rr, name="RR",
                                   line=dict(color="#73BF69", width=1.5),
                                   hovertemplate="%{y:.0f}/min<extra>RR</extra>",
                                   yaxis="y2"))
    multi_layout = {**GRAPH_LAYOUT}
    multi_layout["legend"] = dict(orientation="h", y=1.1, x=0, bgcolor="rgba(0,0,0,0)")
    multi_layout["yaxis"]  = dict(gridcolor="#21262d", title="SpO₂ %")
    multi_layout["yaxis2"] = dict(overlaying="y", side="right", gridcolor="#21262d", title="RR")
    fig_multi.update_layout(**multi_layout)

    # Assessment
    reasoning = assessment.get("clinical_reasoning", "")
    recommendation = assessment.get("recommendation", "")
    key_concerns = assessment.get("key_concerns", "")
    if reasoning or recommendation:
        assess_content = html.Div([
            html.Div([
                html.Div("Clinical Reasoning", style={"fontWeight": 600, "fontSize": "0.78rem",
                                                       "color": "#bc8cff", "marginBottom": "4px"}),
                html.Div(reasoning, style={"fontSize": "0.82rem", "lineHeight": "1.6",
                                           "color": "#adbac7", "whiteSpace": "pre-wrap"}),
            ], style={"marginBottom": "0.8rem"}) if reasoning else html.Div(),
            html.Div([
                html.Div("Key Concerns", style={"fontWeight": 600, "fontSize": "0.78rem",
                                                 "color": "#f0883e", "marginBottom": "4px"}),
                html.Div(key_concerns, style={"fontSize": "0.82rem", "lineHeight": "1.6",
                                               "color": "#adbac7", "whiteSpace": "pre-wrap"}),
            ], style={"marginBottom": "0.8rem"}) if key_concerns else html.Div(),
            html.Div([
                html.Div("Recommendation", style={"fontWeight": 600, "fontSize": "0.78rem",
                                                   "color": "#58a6ff", "marginBottom": "4px"}),
                html.Div(recommendation, style={"fontSize": "0.82rem", "lineHeight": "1.6",
                                                 "color": "#adbac7", "whiteSpace": "pre-wrap"}),
            ]) if recommendation else html.Div(),
        ])
    else:
        assess_content = html.Div("Awaiting MedGemma assessment...", className="no-data")

    # Alerts
    alerts = get_alerts(patient_id, limit=8)
    if not alerts:
        alerts_content = html.Div("No active alerts.", className="no-data")
    else:
        alert_items = []
        for a in alerts:
            sev = a["severity"]
            cls = f"alert-{sev}" if sev in ("critical", "warning") else "alert-info"
            icon = "bi-exclamation-octagon" if sev == "critical" else (
                "bi-exclamation-triangle" if sev == "warning" else "bi-info-circle")
            color = "#f85149" if sev == "critical" else ("#f0883e" if sev == "warning" else "#58a6ff")
            t = a["time"]
            ts = t.astimezone(timezone.utc).strftime("%H:%M") if t else ""
            alert_items.append(html.Div([
                html.I(className=f"bi {icon}", style={"color": color, "minWidth": "16px"}),
                html.Div([
                    html.Div(a["message"], style={"fontSize": "0.8rem"}),
                    html.Div(ts, style={"fontSize": "0.7rem", "color": "#484f58"}),
                ]),
            ], className=f"alert-card {cls}"))
        alerts_content = html.Div(alert_items,
                                   style={"maxHeight": "260px", "overflowY": "auto"})

    # SOAP report
    rpt_time, rpt_text = get_clinician_report(patient_id)
    if rpt_text:
        ts = rpt_time.astimezone(timezone.utc).strftime("%b %d %Y, %H:%M UTC") if rpt_time else ""
        soap_content = html.Div([
            html.Div(f"Generated: {ts}",
                     style={"fontSize": "0.72rem", "color": "#484f58", "marginBottom": "0.5rem"}),
            html.Div(rpt_text, className="soap-report"),
        ])
    else:
        soap_content = html.Div("No clinician report generated yet. "
                                 "Reports appear after the first warning/critical event.",
                                 className="no-data")

    return (risk_card, nyha_card, flags_card,
            fig_hr, fig_multi,
            assess_content, alerts_content if alerts else alerts_content,
            soap_content)
