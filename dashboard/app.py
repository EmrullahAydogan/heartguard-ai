"""HeartGuard AI - Dash Dashboard
Real-time cardiac monitoring powered by MedGemma AI.
"""

import dash
from dash import dcc, html, Input, Output, State, callback, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import timezone
import os

from data_client import (
    get_vitals_timeseries, get_latest_vitals, get_risk_score,
    get_patient_messages, get_medgemma_assessment, get_alerts,
    get_clinician_report, get_nyha_class, get_patient_profile,
    get_all_patients_latest, delete_all_data, PATIENTS
)
import requests
import json
import logging
from kafka import KafkaProducer

try:
    kafka_broker = os.environ.get("KAFKA_BROKER", "localhost:29092")
    dash_producer = KafkaProducer(
        bootstrap_servers=kafka_broker,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    print(f"Dash Kafka Producer connected to {kafka_broker}")
except Exception as e:
    dash_producer = None
    print(f"Warning: Dash Kafka Producer disabled: {e}")

# ── App ──────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.DARKLY,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="HeartGuard AI",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

# Temporary debug middleware to identify crashing callback
from flask import request as flask_request
@server.before_request
def log_callback_request():
    if flask_request.path == "/_dash-update-component":
        try:
            body = flask_request.get_json(silent=True) or {}
            outputs = body.get("output", "?")
            print(f"DISPATCH: output={outputs}", flush=True)
            if "chat-input" in outputs:
                print(f"DEBUG BODY: {json.dumps(body)}", flush=True)
        except Exception as e:
            print(f"DEBUG EXCEPTION: {e}")


# ── Shared constants ──────────────────────────────────────────────────────────

GRAPH_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#8b949e", size=11),
    margin=dict(l=45, r=10, t=10, b=40),
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
CATEGORY_ICON = {
    "stable":   "bi-check-circle-fill",
    "watch":    "bi-eye-fill",
    "warning":  "bi-exclamation-triangle-fill",
    "critical": "bi-exclamation-octagon-fill",
}
STATUS_TEXT = {
    "stable":   "You're Doing Great Today!",
    "watch":    "Things Look Okay — We're Keeping Watch",
    "warning":  "Please Check In With Your Care Team",
    "critical": "Please Contact Your Care Team Now!",
}

# ── Navbar ────────────────────────────────────────────────────────────────────

navbar = dbc.Navbar(
    dbc.Container([
        html.A(
            dbc.Row([
                dbc.Col(html.I(className="bi bi-heart-pulse-fill",
                               style={"color": "#ef4444", "fontSize": "1.4rem"})),
                dbc.Col(dbc.NavbarBrand("HeartGuard AI", className="ms-2")),
            ], align="center", className="g-0"),
            href="/", style={"textDecoration": "none"},
        ),
        dbc.Nav([
            dbc.NavItem(dbc.NavLink(
                [html.I(className="bi bi-heart me-1"), "My Health"],
                href="/patient", active="exact")),
            dbc.NavItem(dbc.NavLink(
                [html.I(className="bi bi-clipboard2-pulse me-1"), "Clinician"],
                href="/clinician", active="exact")),
            dbc.NavItem(dbc.NavLink(
                [html.I(className="bi bi-grid-3x3-gap me-1"), "Command Center"],
                href="/command", active="exact")),
            dbc.NavItem(
                dbc.Button(
                    html.I(className="bi bi-gear-fill", style={"fontSize": "1.1rem"}),
                    id="btn-settings",
                    color="link",
                    style={"padding": "0.5rem", "textDecoration": "none", "color": "var(--text-muted)"},
                    className="ms-2"
                )
            ),
        ], navbar=True, className="ms-auto"),
    ], fluid=True),
    sticky="top", className="navbar",
)

# ── Root layout ───────────────────────────────────────────────────────────────

settings_offcanvas = dbc.Offcanvas(
    html.Div([


        # Database Controls
        html.Div([
            html.Div([
                html.I(className="bi bi-database-exclamation me-2", style={"color": "var(--red)"}),
                "Database Controls",
            ], className="hg-card-title"),
            html.P("Completely wipe the patient database charting history and restart from the beginning.", style={"fontSize": "0.85rem", "color": "var(--text-muted)"}),
            dbc.Button([html.I(className="bi bi-trash3-fill me-1"), "Reset Database"], id="btn-reset", color="danger", className="w-100 mb-2", size="sm"),
            html.Div(id="reset-status", className="mt-2", style={"color": "var(--red)", "fontSize": "0.85rem", "fontWeight": 600, "textAlign": "center"}),
        ]),
    ]),
    id="settings-offcanvas",
    title="System Settings",
    is_open=False,
    placement="end",
    style={
        "background": "rgba(7, 9, 15, 0.95)",
        "backdrop-filter": "blur(20px)",
        "borderLeft": "1px solid var(--border)",
        "fontFamily": "Outfit, sans-serif"
    }
)

# Global chat UI layout wrapper
chat_ui_wrapper = html.Div([
    html.Div([
        html.I(className="bi bi-chat-right-dots-fill me-2", style={"color": "var(--purple)"}),
        "HeartGuard AI Assistant",
    ], className="hg-card-title"),
    html.Div([
        html.Div(
            id="chat-history-display",
            style={
                "height": "250px", "overflowY": "auto", "padding": "12px", 
                "background": "rgba(0,0,0,0.2)", "borderRadius": "12px 12px 0 0",
                "border": "1px solid var(--border)",
                "borderBottom": "none"
            }
        ),
        html.Div(
            id="chat-loading-indicator",
            style={"display": "none"}
        )
    ], style={"marginBottom": "12px"}),
    html.Div([
        dcc.Textarea(
            id="chat-input",
            placeholder="Ask a question about this patient...",
            style={
                "flex": "1",
                "background": "rgba(255,255,255,0.05)",
                "border": "1px solid var(--border)",
                "borderRadius": "10px 0 0 10px",
                "color": "var(--text-primary)",
                "padding": "10px 14px",
                "fontSize": "0.95rem",
                "outline": "none",
                "width": "100%",
                "minHeight": "42px",
                "maxHeight": "150px",
                "resize": "vertical",
                "fontFamily": "Outfit, sans-serif"
            }
        ),
        dbc.Button("Send", id="chat-send-btn", color="primary", n_clicks=0,
                   style={"borderRadius": "0 10px 10px 0", "whiteSpace": "nowrap", "padding": "8px 20px"}),
    ], style={"display": "flex", "gap": "0", "width": "100%"}),
], className="hg-card", id="global-chat-container", style={"display": "none"})

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="patient-store", data="341781"),
    dcc.Store(id="clin-store",    data="341781"),
    dcc.Store(id="chat-history-store", data={"pid": None, "messages": [], "last_clicks": 0}),
    dcc.Interval(id="interval-fast", interval=2000, n_intervals=0),
    dcc.Interval(id="interval-slow", interval=10000, n_intervals=0),

    navbar,
    settings_offcanvas,
    dbc.Container(id="page-content", fluid=True, style={"padding": "0"}),
    dbc.Container(chat_ui_wrapper, fluid=True, style={"paddingTop": "1rem"}),
])

# ── Router ────────────────────────────────────────────────────────────────────

@app.callback(
    Output("page-content", "children"), 
    Output("global-chat-container", "style"),
    Input("url", "pathname")
)
def route(pathname):
    chat_style = {"display": "none"}
    if pathname in ("/patient", "/"):
        return patient_layout(), chat_style
    elif pathname == "/clinician":
        return clinician_layout(), {"display": "block", "marginBottom": "2rem"}
    elif pathname == "/command":
        return command_layout(), chat_style
    return html.Div("Page not found", style={"textAlign": "center", "padding": "3rem",
                                              "color": "#8b949e"}), chat_style

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — MY HEALTH (Patient Portal)
# ══════════════════════════════════════════════════════════════════════════════

def _patient_pills(selected):
    pills = []
    for pid, info in PATIENTS.items():
        active = pid == selected
        pills.append(html.Button(
            info["label"],
            id={"type": "pat-pill", "pid": pid},
            n_clicks=0,
            className=f"patient-pill {'selected' if active else ''}"
        ))
    return pills

def patient_layout():
    return dbc.Container([
        html.Div([
            html.Div("Select Patient", className="hg-card-title mb-2"),
            html.Div(id="pat-pills-container"),
        ], className="hg-card mt-3"),
        html.Div(id="pat-banner"),
        dbc.Row(id="pat-stats", className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("Heartbeat Over Time", className="hg-card-title"),
                dcc.Graph(id="pat-chart-hr", config={"displayModeBar": False},
                          style={"height": "220px"}),
            ], className="hg-card"), xs=12, lg=7),
            dbc.Col(html.Div([
                html.Div("Blood Oxygen Over Time", className="hg-card-title"),
                dcc.Graph(id="pat-chart-spo2", config={"displayModeBar": False},
                          style={"height": "220px"}),
            ], className="hg-card"), xs=12, lg=5),
        ], className="g-3 mb-3"),
        html.Div([
            html.Div([
                html.I(className="bi bi-chat-heart me-2", style={"color": "#58a6ff"}),
                "Messages From Your Care Team",
            ], className="hg-card-title"),
            html.Div(id="pat-messages"),
        ], className="hg-card"),
        html.Div(
            "Your care team reviews this data regularly. If you feel unwell, "
            "please contact your remote care team directly. "
            "HeartGuard AI — Keeping Watch So You Can Rest Easy.",
            style={"textAlign": "center", "color": "#484f58",
                   "fontSize": "0.75rem", "padding": "1rem 0 2rem"},
        ),
    ], fluid=True, style={"paddingTop": "1rem"})


@app.callback(Output("patient-store", "data"),
              Input({"type": "pat-pill", "pid": "341781"}, "n_clicks"),
              Input({"type": "pat-pill", "pid": "447543"}, "n_clicks"),
              Input({"type": "pat-pill", "pid": "3141080"}, "n_clicks"),
              State("patient-store", "data"),
              prevent_initial_call=True)
def pat_select(c1, c2, c3, current):
    if not ctx.triggered_id:
        return current
    if not ctx.triggered[0]["value"]:
        return dash.no_update
    return ctx.triggered_id["pid"]


@app.callback(
    Output("pat-pills-container", "children"),
    Output("pat-banner",    "children"),
    Output("pat-stats",     "children"),
    Output("pat-chart-hr",  "figure"),
    Output("pat-chart-spo2","figure"),
    Output("pat-messages",  "children"),
    Input("interval-fast",  "n_intervals"),
    Input("patient-store",  "data"),
)
def update_patient(_, pid):
    # Pills
    pills = _patient_pills(pid)

    # Status banner
    score, category = get_risk_score(pid)
    category = category or "stable"
    color = CATEGORY_COLOR[category]
    health_pct = round((1.0 - (score or 0.5)) * 100)
    banner_icon = CATEGORY_ICON[category]
    banner_text = STATUS_TEXT[category]

    banner = html.Div([
        html.Div([
            html.I(className=f"bi {banner_icon} me-2"),
            html.Span(banner_text),
        ], style={"fontSize": "1.6rem", "fontWeight": 700}),
        html.Div(f"Heart Health Score: {health_pct}%",
                 style={"fontSize": "0.95rem", "opacity": 0.8, "marginTop": "4px"}),
    ], className=f"status-banner bg-{category}", style={"color": color})

    # Vital stats
    v = get_latest_vitals(pid)
    def stat_card(icon, color, label, val, unit):
        display = f"{val:.0f}" if val is not None else "—"
        return dbc.Col(html.Div([
            html.Div([html.I(className=f"bi {icon} me-2",
                             style={"color": color}), label],
                      className="hg-card-title"),
            html.Div([
                html.Span(display, className="stat-value", style={"color": color}),
                html.Span(unit, className="stat-unit"),
            ]),
        ], className="hg-card"), xs=6, sm=3)

    stats = [
        stat_card("bi-heart-fill",   "#f85149", "Heart Rate",    v.get("heart_rate"),   "bpm"),
        stat_card("bi-droplet-fill", "#5794F2", "Blood Oxygen",  v.get("spo2"),         "%"),
        stat_card("bi-thermometer",  "#FADE2A", "Temperature",   v.get("temperature"),  "°C"),
        stat_card("bi-lungs-fill",   "#73BF69", "Breathing Rate",v.get("respiration"),  "/min"),
    ]

    # HR chart
    times_hr, vals_hr = get_vitals_timeseries(pid, "heart_rate")
    fig_hr = go.Figure(go.Scatter(
        x=times_hr, y=vals_hr, mode="lines",
        line=dict(color="#f85149", width=2),
        fill="tozeroy", fillcolor="rgba(248,81,73,0.08)",
        hovertemplate="%{y:.0f} bpm<extra></extra>",
    ))
    fig_hr.update_layout(**GRAPH_LAYOUT)
    fig_hr.update_yaxes(title_text="bpm")

    # SpO2 chart
    times_sp, vals_sp = get_vitals_timeseries(pid, "spo2")
    fig_sp = go.Figure(go.Scatter(
        x=times_sp, y=vals_sp, mode="lines",
        line=dict(color="#5794F2", width=2),
        fill="tozeroy", fillcolor="rgba(87,148,242,0.08)",
        hovertemplate="%{y:.0f}%<extra></extra>",
    ))
    fig_sp.update_layout(**GRAPH_LAYOUT)
    fig_sp.update_yaxes(title_text="%", range=[70, 100])

    # Messages
    msgs = get_patient_messages(pid, limit=5)
    if not msgs:
        msg_div = html.Div("No messages yet from your care team.", className="no-data")
    else:
        msg_div = [html.Div([
            dcc.Markdown(text, style={"lineHeight": "1.7", "fontSize": "0.95rem"}),
            html.Div(t.astimezone(timezone.utc).strftime("%b %d, %Y  %H:%M UTC") if t else "",
                     style={"fontSize": "0.72rem", "color": "#8b949e", "marginTop": "4px"}),
        ], className="message-card") for t, text in msgs]

    return pills, banner, stats, fig_hr, fig_sp, msg_div


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — CLINICIAN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def _clin_pills(selected):
    pills = []
    for pid, info in PATIENTS.items():
        active = pid == selected
        pills.append(html.Button(
            f"{info['label']} — {info['type']}",
            id={"type": "clin-pill", "pid": pid},
            n_clicks=0,
            style={
                "display": "inline-block",
                "padding": "6px 16px",
                "borderRadius": "20px",
                "fontSize": "0.82rem",
                "fontWeight": 600,
                "cursor": "pointer",
                "marginRight": "8px",
                "border": f"1px solid {'#bc8cff' if active else '#30363d'}",
                "color": "#bc8cff" if active else "#8b949e",
                "background": "#bc8cff22" if active else "#161b22",
            }
        ))
    return pills

def clinician_layout():
    return dbc.Container([
        html.Div([
            html.I(className="bi bi-clipboard2-pulse me-2", style={"color": "#bc8cff"}),
            "Clinician Dashboard",
        ], className="page-title mt-3"),
        html.Div([
            html.Div("Select Patient", className="hg-card-title mb-2"),
            html.Div(id="clin-pills-container"),
        ], className="hg-card"),

        # Clinical Header (Patient Demographics Banner)
        html.Div(id="clin-banner", className="mb-3"),

        dbc.Row([
            # Left Column: Patient Context
            dbc.Col([
                html.Div([
                    html.Div([
                        html.I(className="bi bi-person-lines-fill me-2", style={"color": "#58a6ff"}),
                        "Patient Context & Vitals Baseline"
                    ], className="hg-card-title"),
                    html.Div(id="clin-context-baselines", className="mb-3"),
                    html.Div("Recent Labs", className="hg-card-title", style={"marginTop": "1rem"}),
                    html.Div(id="clin-context-labs", className="mb-3"),
                    html.Div("Active Medications", className="hg-card-title", style={"marginTop": "1rem"}),
                    html.Div(id="clin-context-meds", className="mb-3"),
                    html.Div("Comorbidities", className="hg-card-title", style={"marginTop": "1rem"}),
                    html.Div(id="clin-context-comorb"),
                ], className="hg-card", style={"height": "100%"}),
            ], xs=12, lg=4),

            # Right Column: Monitoring & Decision Support
            dbc.Col([
                dbc.Row([
                    dbc.Col(html.Div(id="clin-risk-card"),  xs=12, md=6),
                    dbc.Col(html.Div(id="clin-nyha-card"),  xs=12, md=6),
                ], className="g-3 mb-3"),
                
                dbc.Row([
                    dbc.Col(html.Div([
                        html.Div("Heart Rate", className="hg-card-title"),
                        dcc.Graph(id="clin-chart-hr", config={"displayModeBar": False},
                                  style={"height": "160px"}),
                    ], className="hg-card"), xs=12, xl=6),
                    dbc.Col(html.Div([
                        html.Div("SpO₂ & Respiratory Rate", className="hg-card-title"),
                        dcc.Graph(id="clin-chart-multi", config={"displayModeBar": False},
                                  style={"height": "160px"}),
                    ], className="hg-card"), xs=12, xl=6),
                ], className="g-3 mb-3"),

                dbc.Row([
                    dbc.Col(html.Div([
                        html.Div([
                            html.I(className="bi bi-robot me-2", style={"color": "#bc8cff"}),
                            "MedGemma AI Assessment",
                        ], className="hg-card-title"),
                        html.Div(id="clin-assessment"),
                    ], className="hg-card", style={"height": "100%"}), xs=12, lg=7),
                    dbc.Col(html.Div([
                        html.Div([
                            html.I(className="bi bi-bell me-2", style={"color": "#f0883e"}),
                            "Active Alerts",
                        ], className="hg-card-title"),
                        html.Div(id="clin-alerts"),
                    ], className="hg-card", style={"height": "100%"}), xs=12, lg=5),
                ], className="g-3 mb-3"),
                
                html.Div([
                    html.Div([
                        html.I(className="bi bi-file-medical me-2", style={"color": "#58a6ff"}),
                        "Latest Clinician Report (SOAP)",
                    ], className="hg-card-title"),
                    html.Div(id="clin-soap"),
                ], className="hg-card", style={"marginBottom": "1rem"}),
            ], xs=12, lg=8),
        ], className="g-3"),
        
    ], fluid=True, style={"paddingTop": "1rem"})


@app.callback(Output("clin-store", "data"),
              Input({"type": "clin-pill", "pid": "341781"}, "n_clicks"),
              Input({"type": "clin-pill", "pid": "447543"}, "n_clicks"),
              Input({"type": "clin-pill", "pid": "3141080"}, "n_clicks"),
              State("clin-store", "data"),
              prevent_initial_call=True)
def clin_select(c1, c2, c3, current):
    if not ctx.triggered_id:
        return current
    if not ctx.triggered[0]["value"]:
        return dash.no_update
    return ctx.triggered_id["pid"]


@app.callback(
    Output("clin-pills-container",   "children"),
    Output("clin-banner",            "children"),
    Output("clin-context-baselines", "children"),
    Output("clin-context-labs",      "children"),
    Output("clin-context-meds",      "children"),
    Output("clin-context-comorb",    "children"),
    Output("clin-risk-card",         "children"),
    Output("clin-nyha-card",         "children"),
    Output("clin-chart-hr",          "figure"),
    Output("clin-chart-multi",       "figure"),
    Output("clin-assessment",        "children"),
    Output("clin-alerts",            "children"),
    Output("clin-soap",              "children"),
    Input("interval-fast", "n_intervals"),
    Input("interval-slow", "n_intervals"),
    Input("clin-store",    "data"),
)
def update_clinician(_, _2, pid):
    pills = _clin_pills(pid)
    prof = get_patient_profile(pid)
    
    # 1. Clinical Header / Banner
    age = prof.get("age", "Unknown")
    gender = prof.get("gender", "Unknown")
    unit = prof.get("unit_type", "Unknown Unit")
    dx = prof.get("primary_dx", "Diagnosis unavailable").replace("|", " > ").title()
    
    clin_banner = html.Div([
        html.Div([
            html.Div(f"Patient {PATIENTS.get(pid, {}).get('label', '')[-1]}", style={"fontSize": "1.6rem", "fontWeight": 700}),
            html.Div(f"ID: {pid} • {age}yr {gender} • {unit}", style={"fontSize": "0.95rem", "color": "#cbd5e1", "marginTop": "4px"}),
            html.Div(f"Admit Dx: {dx}", style={"fontSize": "0.85rem", "color": "#94a3b8", "marginTop": "4px"}),
        ], style={"flex": 1}),
    ], className="hg-card mb-3", style={
        "padding": "1rem 1.4rem",
        "display": "flex",
        "alignItems": "center"
    })

    # 2. Left Column Context
    # Baselines
    base = prof.get("baselines", {})
    hr_b = base.get("hr_mean")
    sp_b = base.get("spo2_mean")
    rr_b = base.get("rr_mean")
    b_items = []
    if hr_b: b_items.append(html.Div(f"HR: ~{hr_b:.0f} bpm", className="badge bg-secondary me-1"))
    if sp_b: b_items.append(html.Div(f"SpO₂: ~{sp_b:.0f}%", className="badge bg-secondary me-1"))
    if rr_b: b_items.append(html.Div(f"RR: ~{rr_b:.0f} /min", className="badge bg-secondary me-1"))
    baselines_div = html.Div(b_items if b_items else "No baseline available", style={"fontSize": "0.85rem", "color": "#8b949e"})

    # Labs
    labs = prof.get("latest_labs", {})
    l_items = []
    for k, v in labs.items():
        if v is not None:
            l_items.append(html.Div([html.Strong(f"{k.capitalize()}: "), f"{v}"], style={"fontSize": "0.85rem", "color": "#c9d1d9", "marginBottom": "2px"}))
    labs_div = html.Div(l_items if l_items else "No recent labs", style={"padding": "8px", "background": "#0d1117", "borderRadius": "6px", "border": "1px solid #30363d"})

    # Meds
    meds = prof.get("medications", [])
    m_items = []
    for m in meds[:6]:
        m_items.append(html.Div([
            html.Span(f"{m.get('name', '')} {m.get('dose', '')}", style={"fontWeight": 600, "color": "#bc8cff"}),
            html.Span(f" - {m.get('route', '')} {m.get('frequency', '')}", style={"color": "#8b949e"})
        ], style={"fontSize": "0.8rem", "marginBottom": "4px", "borderBottom": "1px solid #21262d", "paddingBottom": "2px"}))
    meds_div = html.Div(m_items if m_items else "No active medications listed.")

    # Comorbidities
    comorbs = prof.get("comorbidities", [])
    c_items = []
    for c in comorbs[:5]:
        friendly = c.split("|")[-1].capitalize()
        c_items.append(html.Div(f"• {friendly}", style={"fontSize": "0.82rem", "color": "#8b949e", "marginBottom": "2px"}))
    comorb_div = html.Div(c_items if c_items else "No known comorbidities.")

    # 3. Right Column Monitoring
    score, category = get_risk_score(pid)
    category = category or "stable"
    color = CATEGORY_COLOR[category]
    health_pct = round((1.0 - (score or 0.5)) * 100)

    # Risk card (gauge)
    risk_card = html.Div([
        html.Div("HeartGuard Risk Score", className="hg-card-title"),
        html.Span(f"{health_pct}%", style={"fontSize": "2rem", "fontWeight": 700, "color": color}),
        html.Span(f"  {category.upper()}",
                  style={"fontSize": "0.8rem", "color": color, "fontWeight": 700}),
        dcc.Graph(
            figure=go.Figure(go.Indicator(
                mode="gauge+number",
                value=health_pct,
                number={"suffix": "%", "font": {"color": color, "size": 20}},
                gauge=dict(
                    axis=dict(range=[0, 100], tickcolor="#484f58"),
                    bar=dict(color=color, thickness=0.3),
                    bgcolor="rgba(0,0,0,0)",
                    bordercolor="#30363d",
                    steps=[
                        dict(range=[0, 20],   color="rgba(248,81,73,0.12)"),
                        dict(range=[20, 40],  color="rgba(240,136,62,0.12)"),
                        dict(range=[40, 70],  color="rgba(210,153,34,0.12)"),
                        dict(range=[70, 100], color="rgba(63,185,80,0.12)"),
                    ],
                ),
            )).update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8b949e"),
                margin=dict(l=20, r=20, t=10, b=10),
                height=130,
            ),
            config={"displayModeBar": False},
            style={"height": "130px"},
        ),
    ], className="hg-card", style={"height": "100%"})

    # NYHA card
    nyha = get_nyha_class(pid)
    nyha_card = html.Div([
        html.Div("NYHA Classification", className="hg-card-title"),
        html.Div(f"Class {nyha}" if nyha else "—",
                 style={"fontSize": "2.8rem", "fontWeight": 700, "color": "#bc8cff",
                        "lineHeight": 1, "marginBottom": "6px"}),
        html.Div("Heart Failure Severity", style={"fontSize": "0.78rem", "color": "#8b949e"}),
    ], className="hg-card", style={"height": "100%"})

    # HR chart
    t_hr, v_hr = get_vitals_timeseries(pid, "heart_rate")
    fig_hr = go.Figure(go.Scatter(x=t_hr, y=v_hr, mode="lines",
                                   line=dict(color="#f85149", width=1.5),
                                   fill="tozeroy", fillcolor="rgba(248,81,73,0.07)",
                                   hovertemplate="%{y:.0f} bpm<extra></extra>"))
    fig_hr.update_layout(**GRAPH_LAYOUT)
    fig_hr.update_layout(margin=dict(l=35, r=10, t=10, b=30))

    # Multi chart (SpO2 + RR)
    t_sp, v_sp = get_vitals_timeseries(pid, "spo2")
    t_rr, v_rr = get_vitals_timeseries(pid, "respiration")
    fig_multi = go.Figure()
    fig_multi.add_trace(go.Scatter(x=t_sp, y=v_sp, name="SpO₂",
                                    line=dict(color="#5794F2", width=1.5),
                                    hovertemplate="%{y:.0f}%<extra>SpO₂</extra>"))
    fig_multi.add_trace(go.Scatter(x=t_rr, y=v_rr, name="RR", yaxis="y2",
                                    line=dict(color="#73BF69", width=1.5),
                                    hovertemplate="%{y:.0f}/min<extra>RR</extra>"))
    ml = {**GRAPH_LAYOUT,
          "legend": dict(orientation="h", y=1.15, x=0, bgcolor="rgba(0,0,0,0)"),
          "yaxis2": dict(overlaying="y", side="right", gridcolor="#21262d")}
    ml["yaxis"] = dict(gridcolor="#21262d")
    ml["margin"] = dict(l=35, r=35, t=10, b=30)
    fig_multi.update_layout(**ml)

    # Assessment section
    assessment = get_medgemma_assessment(pid)
    reasoning = assessment.get("clinical_reasoning", "")
    key_concerns = assessment.get("key_concerns", "")
    recommendation = assessment.get("recommendation", "")
    if reasoning or recommendation:
        def section(label, text, color):
            return html.Div([
                html.Div(label, style={"fontWeight": 600, "fontSize": "0.75rem",
                                        "color": color, "marginBottom": "6px",
                                        "textTransform": "uppercase", "letterSpacing": "0.06em"}),
                dcc.Markdown(text, style={"fontSize": "0.95rem", "lineHeight": "1.75",
                                       "color": "#c9d1d9", "marginBottom": "1.2rem"}),
            ])
        assess_content = html.Div([
            section("Clinical Reasoning",  reasoning,       "#bc8cff") if reasoning    else None,
            section("Key Concerns",         key_concerns,    "#f0883e") if key_concerns  else None,
            section("Recommendation",       recommendation,  "#58a6ff") if recommendation else None,
        ])
    else:
        assess_content = html.Div("Awaiting MedGemma assessment...", className="no-data")

    # Alerts
    alerts = get_alerts(pid, limit=8)
    if not alerts:
        alerts_div = html.Div("No active alerts.", className="no-data")
    else:
        items = []
        for a in alerts:
            sev = a["severity"]
            color_a = "#f85149" if sev == "critical" else ("#f0883e" if sev == "warning" else "#58a6ff")
            icon_a  = "bi-exclamation-octagon" if sev == "critical" else (
                      "bi-exclamation-triangle" if sev == "warning" else "bi-info-circle")
            cls = f"alert-{sev}" if sev in ("critical", "warning") else "alert-info"
            t = a["time"]
            ts = t.astimezone(timezone.utc).strftime("%H:%M") if t else ""
            items.append(html.Div([
                html.I(className=f"bi {icon_a}", style={"color": color_a, "minWidth": "16px"}),
                html.Div([
                    html.Div(a["message"], style={"fontSize": "0.8rem"}),
                    html.Div(ts, style={"fontSize": "0.7rem", "color": "#484f58"}),
                ]),
            ], className=f"alert-card {cls}"))
        alerts_div = html.Div(items, style={"maxHeight": "260px", "overflowY": "auto"})

    # SOAP report
    rpt_time, rpt_text = get_clinician_report(pid)
    if rpt_text:
        ts = rpt_time.astimezone(timezone.utc).strftime("%b %d %Y, %H:%M UTC") if rpt_time else ""
        soap_div = html.Div([
            html.Div(f"Generated: {ts}",
                     style={"fontSize": "0.72rem", "color": "#484f58", "marginBottom": "6px"}),
            dcc.Markdown(rpt_text, className="soap-report"),
        ])
    else:
        soap_div = html.Div(
            "No clinician report yet. Reports appear after the first warning/critical event.",
            className="no-data")

    return (pills, clin_banner, baselines_div, labs_div, meds_div, comorb_div,
            risk_card, nyha_card, fig_hr, fig_multi, assess_content, alerts_div, soap_div)

# --- Chatbot Callback ---

def render_chat_bubbles(history):
    chat_ui = []
    for msg in history:
        is_user = msg["role"] == "user"
        bg_col = "var(--purple)" if is_user else "rgba(255,255,255,0.08)"
        text_col = "#ffffff" if is_user else "var(--text-primary)"
        float_dir = "right" if is_user else "left"
        chat_ui.append(html.Div(
            dcc.Markdown(msg["content"], style={"margin": 0}),
            style={
                "padding": "10px 15px", "borderRadius": "16px",
                "backgroundColor": bg_col, "color": text_col,
                "marginBottom": "10px", "maxWidth": "85%",
                "display": "inline-block", "clear": "both",
                "float": float_dir, "wordWrap": "break-word",
                "boxShadow": "var(--glow-purple)" if is_user else "none",
                "border": "1px solid var(--border)" if not is_user else "none",
                "fontSize": "0.9rem"
            }
        ))
        chat_ui.append(html.Div(style={"clear": "both"}))
    return chat_ui

@app.callback(
    Output("chat-input", "value"),
    Output("chat-loading-indicator", "style", allow_duplicate=True),
    Output("chat-loading-indicator", "children", allow_duplicate=True),
    Output("chat-history-display", "children", allow_duplicate=True),
    Input("chat-send-btn", "n_clicks"),
    State("chat-input", "value"),
    State("chat-history-store", "data"),
    prevent_initial_call=True
)
def clear_chat_input_and_show_thinking(n, text, history_dict):
    if not text or not text.strip():
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    thinking_style = {
        "display": "block",
        "padding": "8px 12px",
        "background": "rgba(0,0,0,0.2)",
        "border": "1px solid var(--border)",
        "borderTop": "none",
        "borderRadius": "0 0 12px 12px",
        "color": "var(--text-muted)",
        "fontStyle": "italic",
        "fontSize": "0.85rem"
    }
    thinking_content = html.Div([
        html.I(className="bi bi-robot me-2"),
        "MedGemma is thinking..."
    ])
    
    history = list(history_dict.get("messages", [])) if isinstance(history_dict, dict) else []
    history.append({"role": "user", "content": text})
    chat_ui = render_chat_bubbles(history)
    
    return "", thinking_style, thinking_content, chat_ui

@app.callback(
    Output("chat-history-store", "data"),
    Output("chat-history-display", "children"),
    Output("chat-loading-indicator", "style"),
    Input("chat-send-btn", "n_clicks"),
    Input("clin-store", "data"),
    State("chat-input", "value"),
    State("chat-history-store", "data"),
    prevent_initial_call=True
)
def handle_chat(n_clicks, pid, user_msg, history_dict):
    trigger = ctx.triggered_id
    n_clicks = n_clicks or 0

    hide_thinking = {"display": "none"}

    if not isinstance(history_dict, dict):
        history_dict = {"pid": pid, "messages": [], "last_clicks": 0}

    last_pid = history_dict.get("pid")
    history = list(history_dict.get("messages", []))
    last_clicks = history_dict.get("last_clicks", 0)

    # Patient switched → clear chat
    if trigger == "clin-store":
        if last_pid is not None and last_pid != pid:
            return {"pid": pid, "messages": [], "last_clicks": n_clicks}, html.Div(
                "Chat context cleared. Ask a question about the new patient.",
                style={"color": "#8b949e", "fontStyle": "italic"}
            ), hide_thinking
        return dash.no_update, dash.no_update, dash.no_update

    if trigger != "chat-send-btn":
        return dash.no_update, dash.no_update, dash.no_update

    # Guard: only process if this is genuinely a NEW click
    if n_clicks <= last_clicks:
        return dash.no_update, dash.no_update, dash.no_update

    print(f"DEBUG CHAT: new submit! clicks={n_clicks}, msg={repr(user_msg)}")

    if not user_msg or not user_msg.strip():
        return {**history_dict, "last_clicks": n_clicks}, dash.no_update, hide_thinking

    history.append({"role": "user", "content": user_msg})

    # Query MedGemma Server
    try:
        medgemma_url = os.environ.get("MEDGEMMA_URL", "http://172.17.0.1:8888/chat")
        patient_info = PATIENTS.get(pid, {})
        vitals = get_latest_vitals(pid)
        score, cat = get_risk_score(pid)
        # Always inject real-time physical context secretly to prevent LLM amnesia
        sys_context = f"[System Context: You are currently assisting the clinician with Patient {patient_info.get('name', 'Unknown')}. Current status: {cat.upper()}, HR: {vitals.get('heart_rate')} bpm, SpO2: {vitals.get('spo2')}%, RR: {vitals.get('respiration')}/min, Temp: {vitals.get('temperature')}C.]\n\n"
        current_prompt = sys_context + user_msg

        print(f"DEBUG CHAT: Calling MedGemma at {medgemma_url}")
        response = requests.post(medgemma_url, json={
            "prompt": current_prompt,
            "history": history[:-1]
        }, timeout=120)

        if response.status_code == 200:
            bot_text = response.json().get("generated_text", "Sorry, I could not generate a response.")
            print(f"DEBUG CHAT: Got response: {bot_text[:80]}")
        else:
            bot_text = f"Error: {response.status_code} - {response.text}"
            print(f"DEBUG CHAT: Bad status {response.status_code}")

    except Exception as e:
        bot_text = f"Failed to connect to AI server: {str(e)}"
        print(f"DEBUG CHAT: Exception: {e}")

    history.append({"role": "assistant", "content": bot_text})

    chat_ui = render_chat_bubbles(history)

    return {"pid": pid, "messages": history, "last_clicks": n_clicks}, chat_ui, hide_thinking


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — COMMAND CENTER
# ══════════════════════════════════════════════════════════════════════════════

def command_layout():
    return dbc.Container([
        html.Div([
            html.I(className="bi bi-grid-3x3-gap me-2", style={"color": "#58a6ff"}),
            "Command Center — All Patients",
        ], className="page-title mt-3"),
        
        dbc.Row(id="cmd-cards", className="g-3 mb-3"),
        html.Div([
            html.I(className="bi bi-activity me-2", style={"color": "#3fb950"}),
            "Heart Rate Trends",
        ], style={"fontWeight": 600, "fontSize": "0.8rem", "color": "#8b949e",
                  "marginBottom": "8px", "textTransform": "uppercase"}),
        dbc.Row(id="cmd-trends", className="g-3 mb-3"),
        html.Div([
            html.I(className="bi bi-bell-fill me-2", style={"color": "#f0883e"}),
            "Recent Alerts — All Patients",
        ], style={"fontWeight": 600, "fontSize": "0.8rem", "color": "#8b949e",
                  "marginBottom": "8px", "textTransform": "uppercase"}),
        html.Div(id="cmd-alerts", className="hg-card"),
        html.Div(id="cmd-footer", className="hg-card mt-3"),
    ], fluid=True, style={"paddingTop": "1rem"})





@app.callback(
    Output("reset-status", "children"),
    Input("btn-reset", "n_clicks"),
    prevent_initial_call=True
)
def reset_database(n_clicks):
    if not n_clicks:
        return dash.no_update
        
    success = delete_all_data()
    if not success:
        return "Failed to wipe InfluxDB."
        
    try:
        if dash_producer:
            dash_producer.send("chf.control", value={"action": "restart_stream"})
            dash_producer.flush()
            return "Wiped DB & Restarted Stream!"
        return "Wiped DB, but Kafka publisher not found."
    except Exception as e:
        return f"Wiped DB, Kafka Error: {e}"


@app.callback(
    Output("settings-offcanvas", "is_open"),
    Input("btn-settings", "n_clicks"),
    State("settings-offcanvas", "is_open"),
)
def toggle_settings(n1, is_open):
    if n1:
        return not is_open
    return is_open


@app.callback(
    Output("cmd-cards",  "children"),
    Output("cmd-trends", "children"),
    Output("cmd-alerts", "children"),
    Output("cmd-footer", "children"),
    Input("interval-fast", "n_intervals"),
)
def update_command(_):
    data = get_all_patients_latest()

    # Patient summary cards
    cards = []
    for pid, info in PATIENTS.items():
        d = data.get(pid, {})
        cat = d.get("risk_category", "stable")
        score = d.get("risk_score")
        color = CATEGORY_COLOR.get(cat, "#3fb950")
        icon = CATEGORY_ICON.get(cat, "bi-check-circle-fill")
        v = d.get("vitals", {})
        hp = round((1.0 - (score or 0.5)) * 100)

        def vital_row(ico, col, lbl, val, unit):
            disp = f"{val:.0f}{unit}" if val is not None else "—"
            return html.Div([
                html.I(className=f"bi {ico} me-2", style={"color": col, "fontSize": "0.75rem"}),
                html.Span(lbl + ": ", style={"color": "var(--text-muted)", "fontSize": "0.82rem"}),
                html.Span(disp, style={"fontWeight": 600, "fontSize": "0.82rem", "color": "var(--text-primary)"}),
            ], style={"marginBottom": "4px"})

        cards.append(dbc.Col(html.Div([
            html.Div([
                html.Div([html.I(className=f"bi {icon} me-2", style={"color": color}),
                          html.Span(info["name"], style={"fontWeight": 700, "fontSize": "1rem"})],
                         style={"display": "flex", "alignItems": "center"}),
                html.Div(f"{hp}%", style={"color": color, "fontWeight": 700, "fontSize": "1.2rem"}),
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "10px"}),
            html.Div(cat.upper(), className=f"badge bg-{cat} mb-3", style={"color": color, "fontSize": "0.7rem"}),
            vital_row("bi-heart-fill",   "#ef4444", "HR",   v.get("heart_rate"),  " bpm"),
            vital_row("bi-droplet-fill", "#3b82f6", "SpO₂", v.get("spo2"),        "%"),
            vital_row("bi-thermometer",  "#f59e0b", "Temp", v.get("temperature"), "°C"),
            vital_row("bi-lungs-fill",   "#10b981", "RR",   v.get("respiration"), "/min"),
        ], className="hg-card", style={"border": f"1px solid {color}33"}), xs=12, md=4))

    # Trend charts
    trend_colors = ["#f85149", "#f0883e", "#bc8cff"]
    trends = []
    for (pid, info), col in zip(PATIENTS.items(), trend_colors):
        t, v = get_vitals_timeseries(pid, "heart_rate")
        fig = go.Figure(go.Scatter(x=t, y=v, mode="lines",
                                    line=dict(color=col, width=1.5),
                                    fill="tozeroy",
                                    fillcolor=f"rgba({int(col[1:3],16)},{int(col[3:5],16)},{int(col[5:7],16)},0.07)",
                                    hovertemplate="%{y:.0f} bpm<extra></extra>"))
        fig.update_layout(**{**GRAPH_LAYOUT, "margin": dict(l=35, r=10, t=5, b=30)})
        gl = {**GRAPH_LAYOUT}
        gl["margin"] = dict(l=35, r=10, t=5, b=30)
        gl["xaxis"] = dict(gridcolor="#21262d", showgrid=True, zeroline=False, showticklabels=False)
        fig.update_layout(**gl)
        trends.append(dbc.Col(html.Div([
            html.Div(info["label"], className="hg-card-title"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "150px"}),
        ], className="hg-card"), xs=12, md=4))

    # All alerts
    all_alerts = []
    for pid, info in PATIENTS.items():
        for a in get_alerts(pid, limit=5):
            all_alerts.append({**a, "patient": info["label"]})
    all_alerts.sort(key=lambda x: x["time"] or "", reverse=True)

    if not all_alerts:
        alerts_div = html.Div("No recent alerts.", className="no-data")
    else:
        items = []
        for a in all_alerts[:15]:
            sev = a["severity"]
            col = "#f85149" if sev == "critical" else ("#f0883e" if sev == "warning" else "#58a6ff")
            ico = "bi-exclamation-octagon" if sev == "critical" else (
                  "bi-exclamation-triangle" if sev == "warning" else "bi-info-circle")
            cls = f"alert-{sev}" if sev in ("critical", "warning") else "alert-info"
            t = a["time"]
            ts = t.astimezone(timezone.utc).strftime("%b %d %H:%M") if t else ""
            items.append(html.Div([
                html.I(className=f"bi {ico}", style={"color": col, "minWidth": "16px"}),
                html.Div([
                    html.Span(f"[{a['patient']}] ", style={"fontWeight": 700, "color": col}),
                    html.Span(a["message"], style={"fontSize": "0.8rem"}),
                    html.Div(ts, style={"fontSize": "0.7rem", "color": "#484f58"}),
                ]),
            ], className=f"alert-card {cls}"))
        alerts_div = html.Div(items, style={"maxHeight": "280px", "overflowY": "auto"})

    # Footer stats
    total_alerts = sum(len(get_alerts(p, 100)) for p in PATIENTS)
    critical_n = sum(1 for p in PATIENTS for a in get_alerts(p, 50) if a["severity"] == "critical")
    footer = dbc.Row([
        dbc.Col(html.Div([
            html.I(className="bi bi-people-fill me-2", style={"color": "var(--blue)"}),
            html.Span("Patients: ", style={"color": "var(--text-muted)", "fontSize": "0.9rem"}),
            html.Span(str(len(PATIENTS)), style={"fontWeight": 700, "color": "var(--blue)", "fontSize": "1rem"}),
        ]), xs=12, sm=4),
        dbc.Col(html.Div([
            html.I(className="bi bi-bell-fill me-2", style={"color": "var(--orange)"}),
            html.Span("Total Alerts: ", style={"color": "var(--text-muted)", "fontSize": "0.9rem"}),
            html.Span(str(total_alerts), style={"fontWeight": 700, "color": "var(--orange)", "fontSize": "1rem"}),
        ]), xs=12, sm=4),
        dbc.Col(html.Div([
            html.I(className="bi bi-exclamation-octagon-fill me-2", style={"color": "var(--red)"}),
            html.Span("Critical Issues: ", style={"color": "var(--text-muted)", "fontSize": "0.9rem"}),
            html.Span(str(critical_n), style={"fontWeight": 700, "color": "var(--red)", "fontSize": "1rem"}),
        ]), xs=12, sm=4),
    ], className="g-3 align-items-center mb-4")

    return cards, trends, alerts_div, footer


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9005, debug=False, threaded=True)
