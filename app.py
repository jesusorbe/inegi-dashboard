import os
import json
from datetime import datetime
from functools import lru_cache

import pandas as pd
import plotly.express as px
import requests as rq
from flask import Flask, jsonify, request

# ---------- Flask base app ----------
server = Flask(__name__)

@server.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now().isoformat(timespec="seconds")}


def _validate_filter(filtro: str) -> str:
    """Validate filter in 'YYYY/MM' format; fallback to '2000/01' if bad."""
    try:
        # Accept 'YYYY/MM' or 'YYYY-MM' and normalize to 'YYYY/MM'
        if "/" in filtro:
            dt = datetime.strptime(filtro, "%Y/%m")
        elif "-" in filtro:
            dt = datetime.strptime(filtro, "%Y-%m")
        else:
            # try raw 'YYYYMM'
            dt = datetime.strptime(filtro, "%Y%m")
        return dt.strftime("%Y/%m")
    except Exception:
        return "2000/01"


@lru_cache(maxsize=256)
def _fetch_inegi_series(indicador: str, token: str) -> pd.DataFrame:
    """Call INEGI API and return a tidy DataFrame for the series.

    This function is cached (per-process) to reduce API calls while testing.
    """
    if not token or token.strip() in {"", "TOKEN_AQUI", "\""}:
        raise ValueError("Falta el token del INEGI. Proporciónalo en el dashboard.")

    url = (
        f"https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/"
        f"{indicador}/es/0700/false/BIE/2.0/{token}?type=json"
    )

    try:
        resp = rq.get(url, timeout=30)
    except rq.RequestException as e:
        raise RuntimeError(f"Error de red al consultar INEGI: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"INEGI respondió {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as e:
        raise RuntimeError("No se pudo decodificar JSON de INEGI.") from e

    try:
        series = data.get("Series")[0].get("OBSERVATIONS")
    except Exception as e:
        raise RuntimeError("Estructura inesperada en la respuesta de INEGI.") from e

    df = pd.DataFrame(series)
    if df.empty:
        return df

    # Orden y tipados
    df = df.sort_values(by="TIME_PERIOD").reset_index(drop=True)
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")

    # Algunas series traen ATTRIBUTEs como dict; preservemos lo que haya útil
    # y limpiemos nombres consistentes
    rename_map = {
        "TIME_PERIOD": "periodo",
        "OBS_VALUE": "valor",
        "COBER_GEO": "cobertura_geo",
        "UNIT": "unidad",
    }
    for col_old, col_new in rename_map.items():
        if col_old in df.columns:
            df.rename(columns={col_old: col_new}, inplace=True)

    return df


def get_data(indicador: str, token: str, filtro: str) -> pd.DataFrame:
    filtro_norm = _validate_filter(filtro)
    df = _fetch_inegi_series(str(indicador), token).copy()
    if df.empty:
        return df
    # Filtrado por periodo tipo 'YYYY/MM'
    if "periodo" in df.columns:
        return df[df["periodo"] >= filtro_norm]
    else:
        # fallback a columna original si renombrado no ocurrió
        return df[df["TIME_PERIOD"] >= filtro_norm]


@server.get("/api/series")
def api_series():
    """API JSON: /api/series?indicador=910407&token=XXX&filtro=2005/01"""
    indicador = request.args.get("indicador", type=str, default="910407")
    token = request.args.get("token", type=str, default="")
    filtro = request.args.get("filtro", type=str, default="2005/01")

    try:
        df = get_data(indicador, token, filtro)
        if df.empty:
            return jsonify({
                "indicator": indicador,
                "filtro": _validate_filter(filtro),
                "count": 0,
                "data": [],
                "message": "Sin datos para los parámetros proporcionados"
            })

        # Estándar de salida simple: lista de puntos {x, y}
        if "periodo" in df.columns and "valor" in df.columns:
            records = [
                {"x": p, "y": float(v) if pd.notna(v) else None}
                for p, v in zip(df["periodo"], df["valor"])
            ]
        else:
            records = [
                {"x": p, "y": float(v) if pd.notna(v) else None}
                for p, v in zip(df["TIME_PERIOD"], df["OBS_VALUE"])
            ]

        return jsonify({
            "indicator": indicador,
            "filtro": _validate_filter(filtro),
            "count": len(records),
            "data": records,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------- Dash app (mounted on Flask) ----------
from dash import Dash, dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc

external_stylesheets = [dbc.themes.BOOTSTRAP]

dapp = Dash(
    __name__,
    server=server,
    external_stylesheets=external_stylesheets,
    # app at /dashboard/
    suppress_callback_exceptions=True,
)

def layout_app():
    return dbc.Container([
        html.H1("INEGI Dashboard – Serie BIE"),
        html.P(
            "Consulta una serie de INEGI (BIE) y grafícala. El token se usa únicamente en tu navegador/servidor."
        ),
        dbc.Row([
            dbc.Col([
                dbc.Label("Indicador (ej. 910407)"),
                dbc.Input(id="indicador", type="text", value="910407"),
            ], md=3),
            dbc.Col([
                dbc.Label("Filtro desde (YYYY/MM)"),
                dbc.Input(id="filtro", type="text", value="2005/01"),
            ], md=3),
            dbc.Col([
                dbc.Label("Token INEGI"),
                dbc.Input(id="token", type="password", value=""),
            ], md=4),
            dbc.Col([
                dbc.Label(" "),
                dbc.Button("Actualizar", id="btn", color="primary", className="d-block w-100"),
            ], md=2),
        ], className="gy-2 my-2"),
        dbc.Alert(id="msg", color="info", is_open=False),
        dcc.Loading(
            id="loading",
            type="default",
            children=dcc.Graph(id="grafica", figure={}),
        ),
        html.Hr(),
        html.Small(id="meta", className="text-muted"),
    ], fluid=True)


dapp.layout = layout_app


@dapp.callback(
    Output("grafica", "figure"),
    Output("msg", "children"),
    Output("msg", "is_open"),
    Output("msg", "color"),
    Output("meta", "children"),
    Input("btn", "n_clicks"),
    State("indicador", "value"),
    State("token", "value"),
    State("filtro", "value"),
    prevent_initial_call=False,
)
def actualizar(n_clicks, indicador, token, filtro):
    # Trigger initial load when n_clicks is None as well
    try:
        df = get_data(str(indicador).strip(), str(token).strip(), str(filtro).strip())
        if df.empty:
            fig = px.line(title="Sin datos")
            return fig, "Sin datos para los parámetros.", True, "warning", ""

        # Normaliza columnas
        if {"periodo", "valor"}.issubset(df.columns):
            x = df["periodo"]
            y = df["valor"]
        else:
            x = df["TIME_PERIOD"]
            y = df["OBS_VALUE"]

        fig = px.line(pd.DataFrame({"periodo": x, "valor": y}), x="periodo", y="valor", markers=True,
                      title=f"Indicador {indicador}")
        fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))

        msg = f"{len(x)} observaciones cargadas."
        meta = f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Filtro: {_validate_filter(filtro)}"
        return fig, msg, True, "success", meta
    except Exception as e:
        fig = px.line(title="Error")
        return fig, f"Error: {e}", True, "danger", ""


# ---------- Main ----------
if __name__ == "__main__":
    # You can override the default port with PORT env var
    port = int(os.environ.get("PORT", "8050"))
    # Run the Dash app (which serves via the embedded Flask `server`)
    dapp.run(host="0.0.0.0", port=port, debug=True)
