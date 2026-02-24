"""Patient Portal - My Health page."""

import plotly.graph_objects as go
from dash import dcc, html, callback, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import timezone

from data_client import (
    get_vitals_timeseries, get_latest_vitals, get_risk_score,
    get_patient_messages, PATIENTS
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

STATUS_MAP = {
    "stable":   ("You're Doing Great Today!", "#3fb950", "bi-emoji-smile"),
    "watch":    ("Things Look Okay — We're Keeping Watch", "#d29922", "bi-emoji-neutral"),
    "warning":  ("Please Check In With Your Care Team", "#f0883e", "bi-exclamation-triangle"),
    "critical": ("Please Contact Your Care Team Now!", "#f85149", "bi-exclamation-octagon"),
}

def layout():
    return dbc.Container([
        dcc.Store(id="patient-selected", data="341781"),
        # Patient selector
        html.Div([
            html.Div("Select Patient", className="hg-card-title mb-2"),
            html.Div(id="patient-pills"),
        ], className="hg-card mt-3"),
        # Status banner
        html.Div(id="patient-status-banner"),
        # Row: vitals stats
        dbc.Row(id="patient-vital-stats", className="g-3"),
        # Row: charts
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div("Heartbeat Over Time", className="hg-card-title"),
                    dcc.Graph(id="chart-hr", config={"displayModeBar": False},
                              style={"height": "220px"}),
                ], className="hg-card"),
            ], xs=12, lg=7),
            dbc.Col([
                html.Div([
                    html.Div("Blood Oxygen Over Time", className="hg-card-title"),
                    dcc.Graph(id="chart-spo2", config={"displayModeBar": False},
                              style={"height": "220px"}),
                ], className="hg-card"),
            ], xs=12, lg=5),
        ], className="g-3"),
        # Messages
        html.Div([
            html.Div([
                html.I(className="bi bi-chat-heart me-2", style={"color": "#58a6ff"}),
                "Messages From Your Care Team",
            ], className="hg-card-title"),
            html.Div(id="patient-messages"),
        ], className="hg-card"),
        # Footer
        html.Div(
            "Your care team reviews this data regularly. If you feel unwell, please call your nurse or doctor directly. "
            "HeartGuard AI — Keeping Watch So You Can Rest Easy.",
            style={"textAlign": "center", "color": "#484f58", "fontSize": "0.75rem",
                   "padding": "1rem 0 2rem"},
        ),
    ], fluid=True, style={"paddingTop": "1rem"})


# ── Callbacks ────────────────────────────────────────────────────────────────

@callback(Output("patient-pills", "children"), Input("patient-selected", "data"))
def render_pills(selected):
    pills = []
    for pid, info in PATIENTS.items():
        cls = "patient-pill selected" if pid == selected else "patient-pill"
        pills.append(
            html.Span(info["label"], className=cls, id={"type": "pill", "pid": pid})
        )
    return pills


@callback(
    Output("patient-selected", "data"),
    Input({"type": "pill", "pid": "341781"}, "n_clicks"),
    Input({"type": "pill", "pid": "447543"}, "n_clicks"),
    Input({"type": "pill", "pid": "3141080"}, "n_clicks"),
    State("patient-selected", "data"),
    prevent_initial_call=True,
)
def select_patient(c1, c2, c3, current):
    from dash import ctx
    if not ctx.triggered_id:
        return current
    return ctx.triggered_id["pid"]


@callback(
    Output("patient-status-banner", "children"),
    Output("patient-vital-stats", "children"),
    Output("chart-hr", "figure"),
    Output("chart-spo2", "figure"),
    Output("patient-messages", "children"),
    Input("interval-fast", "n_intervals"),
    Input("patient-selected", "data"),
)
def update_patient(_, patient_id):
    # Status
    score, category = get_risk_score(patient_id)
    category = category or "stable"
    msg, color, icon = STATUS_MAP.get(category, STATUS_MAP["stable"])
    health_pct = round((1.0 - (score or 0.5)) * 100)

    banner = html.Div([
        html.Div([
            html.I(className=f"bi {icon} me-2"),
            html.Span(msg, className="banner-title"),
        ]),
        html.Div(f"Heart Health Score: {health_pct}%", className="banner-sub mt-1"),
    ], className=f"status-banner bg-{category}", style={"borderColor": color, "color": color})

    # Vitals stats
    v = get_latest_vitals(patient_id)
    stats = [
        ("bi-heart-fill",     "#f85149", "Heart Rate",     v.get("heart_rate"),  "bpm"),
        ("bi-droplet-fill",   "#5794F2", "Blood Oxygen",   v.get("spo2"),        "%"),
        ("bi-thermometer",    "#FADE2A", "Temperature",    v.get("temperature"), "°C"),
        ("bi-lungs-fill",     "#73BF69", "Breathing Rate", v.get("respiration"), "/min"),
    ]
    cols = []
    for icon_cls, color, label, val, unit in stats:
        display = f"{val:.0f}" if val is not None else "—"
        cols.append(dbc.Col(
            html.Div([
                html.Div([
                    html.I(className=f"bi {icon_cls} me-2", style={"color": color}),
                    label,
                ], className="hg-card-title"),
                html.Div([
                    html.Span(display, className="stat-value", style={"color": color}),
                    html.Span(unit, className="stat-unit"),
                ]),
            ], className="hg-card"),
            xs=6, sm=3,
        ))
    vital_row = cols

    # HR chart
    times_hr, vals_hr = get_vitals_timeseries(patient_id, "heart_rate")
    fig_hr = go.Figure(go.Scatter(
        x=times_hr, y=vals_hr, mode="lines",
        line=dict(color="#f85149", width=2),
        fill="tozeroy", fillcolor="rgba(248,81,73,0.08)",
        hovertemplate="%{y:.0f} bpm<extra></extra>",
    ))
    fig_hr.update_layout(**GRAPH_LAYOUT)
    fig_hr.update_yaxes(title_text="bpm")

    # SpO2 chart
    times_sp, vals_sp = get_vitals_timeseries(patient_id, "spo2")
    fig_sp = go.Figure(go.Scatter(
        x=times_sp, y=vals_sp, mode="lines",
        line=dict(color="#5794F2", width=2),
        fill="tozeroy", fillcolor="rgba(87,148,242,0.08)",
        hovertemplate="%{y:.0f}%<extra></extra>",
    ))
    fig_sp.update_layout(**GRAPH_LAYOUT)
    fig_sp.update_yaxes(title_text="%", range=[80, 100])

    # Messages
    msgs = get_patient_messages(patient_id, limit=5)
    if not msgs:
        msg_children = html.Div("No messages yet from your care team.", className="no-data")
    else:
        msg_children = [
            html.Div([
                html.Div(text, style={"lineHeight": "1.55"}),
                html.Div(
                    t.astimezone(timezone.utc).strftime("%b %d, %Y  %H:%M UTC") if t else "",
                    className="message-time",
                ),
            ], className="message-card")
            for t, text in msgs
        ]

    return banner, vital_row, fig_hr, fig_sp, msg_children
