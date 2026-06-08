"""
charts.py
---------
Generazione delle figure Plotly a partire da DataFrame già filtrati e aggregati.
Ogni funzione riceve un DataFrame (da db.py) e ritorna un plotly.graph_objects.Figure.

Responsabilità:
- Costruzione delle figure Plotly
- Configurazione estetica (colori, assi, titoli, hover)
- Gestione del caso DataFrame vuoto (figura con messaggio informativo)

NON esegue query al DB né logica di filtro.
"""

import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

# Palette di colori consistente per le persone (ciclica se >10)
_COLOR_SEQUENCE = px.colors.qualitative.Plotly

# Tick fissi per tutti gli assi sentiment: -1 → +1
_SENTIMENT_TICKVALS = [-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0]
_SENTIMENT_TICKTEXT = ["-1.0", "-0.75", "-0.50", "-0.25",
                       "0.00", "+0.25", "+0.50", "+0.75", "+1.0"]


def _empty_figure(message: str) -> go.Figure:
    """Ritorna una figura vuota con un messaggio centrato."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="gray"),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
    )
    return fig


def _base_layout(fig: go.Figure, title: str) -> go.Figure:
    """Applica un layout di base comune a tutte le figure."""
    fig.update_layout(
        height=520,
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=17, color="#222222"),
            x=0.5,
            xanchor="center",
            y=0.97,
            yanchor="top",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif", size=13, color="#333333"),
        showlegend=True,
        legend=dict(
            title=dict(font=dict(size=13, color="#333333")),
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="right",
            x=0.99,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#aaaaaa",
            borderwidth=1,
            font=dict(size=12, color="#222222"),
            itemwidth=40,
        ),
        margin=dict(t=70, b=80, l=90, r=40),
        hovermode="x unified",
    )
    fig.update_xaxes(
        showgrid=True, gridcolor="#e8e8e8",
        linecolor="#bbbbbb", linewidth=1,
        ticks="outside", ticklen=5,
        tickfont=dict(size=12, color="#222222"),
        title_font=dict(size=13, color="#222222"),
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#e8e8e8",
        linecolor="#bbbbbb", linewidth=1,
        ticks="outside", ticklen=5,
        tickfont=dict(size=12, color="#222222"),
        title_font=dict(size=13, color="#222222"),
        automargin=True,
    )
    return fig


def _sentiment_yaxis() -> dict:
    """Configurazione asse Y standard per i grafici di sentiment."""
    return dict(
        title_text="Sentiment medio  (−1 = negativo · 0 = neutro · +1 = positivo)",
        range=[-1.1, 1.1],
        tickvals=_SENTIMENT_TICKVALS,
        ticktext=_SENTIMENT_TICKTEXT,
        tickfont=dict(size=12, color="#222222"),
        zeroline=True,
        zerolinecolor="#aaaaaa",
        zerolinewidth=1,
        automargin=True,
    )


def _date_xaxis(df_giorno: pd.Series) -> dict:
    """
    Configurazione asse X per date.
    Adatta il formato tick alla densità temporale:
    - ≤ 30 giorni  → "DD MMM"
    - ≤ 180 giorni → "DD MMM"  con dtick settimanale
    - > 180 giorni → "MMM YYYY" con dtick mensile
    """
    n_giorni = (df_giorno.max() - df_giorno.min()).days if len(df_giorno) > 1 else 1

    if n_giorni <= 30:
        dtick = 86_400_000          # 1 giorno in millisecondi (formato Plotly per date axis)
        tick_format = "%d %b %Y"
    elif n_giorni <= 180:
        dtick = 7 * 86_400_000      # 1 settimana in millisecondi
        tick_format = "%d %b %Y"
    else:
        dtick = "M1"                # mensile: "M1" è il formato stringa corretto per Plotly
        tick_format = "%b %Y"

    return dict(
        title_text="Data",
        tickformat=tick_format,
        dtick=dtick,
        tickangle=-35,
        ticks="outside",
        ticklen=5,
    )


# ---------------------------------------------------------------------------
# Grafico 1 — Trend temporale del sentiment per persona
# ---------------------------------------------------------------------------

def chart_sentiment_trend(
    df: pd.DataFrame,
    series: list[str],
    label: str | None,
    series_col: str = "persona",
) -> go.Figure:
    """
    Linechart: andamento del sentiment medio nel tempo.

    series:     lista dei valori della colonna series_col da mostrare.
    series_col: colonna del DataFrame che identifica la serie ("persona" o "argomento").
    label:      testo aggiuntivo nel titolo (argomento o persona fissa).

    Input DataFrame atteso: [giorno, {series_col}, sent_medio, totale]
    """
    df = df.copy()
    if not df.empty:
        df["giorno"] = pd.to_datetime(df["giorno"])
        df["sent_medio"] = df["sent_medio"].astype(float)

    series_con_dati: set[str] = set(df[series_col].unique()) if not df.empty else set()
    fig = go.Figure()

    for i, serie in enumerate(series):
        color = _COLOR_SEQUENCE[i % len(_COLOR_SEQUENCE)]

        if serie not in series_con_dati:
            fig.add_trace(go.Scatter(
                x=[], y=[], mode="lines",
                name=f"{serie} (nessun dato)",
                line=dict(width=2, color=color, dash="dot"),
                showlegend=True,
            ))
        else:
            subset = df[df[series_col] == serie].sort_values("giorno")
            fig.add_trace(go.Scatter(
                x=subset["giorno"],
                y=subset["sent_medio"],
                mode="lines+markers",
                name=serie,
                line=dict(width=2.5, color=color),
                marker=dict(size=6, color=color, symbol="circle"),
                customdata=subset[["totale"]].values,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Data: %{x|%d %b %Y}<br>"
                    "Sentiment: %{y:.4f}<br>"
                    "Mention: %{customdata[0]}<extra></extra>"
                ),
            ))

    fig.add_hrect(y0=-0.1, y1=0.1, fillcolor="gray", opacity=0.07, line_width=0)
    fig.add_hline(y=0, line_dash="dash", line_color="#888888", line_width=1.2)

    subtitle = f" — {label}" if label else ""
    _base_layout(fig, f"Trend Sentiment nel Tempo{subtitle}")
    legend_title = "Argomento" if series_col == "argomento" else "Persona"
    fig.update_layout(legend_title_text=legend_title)
    fig.update_yaxes(**_sentiment_yaxis())

    if not df.empty:
        fig.update_xaxes(**_date_xaxis(df["giorno"]))
    else:
        fig.update_xaxes(title_text="Data")

    return fig


# ---------------------------------------------------------------------------
# Grafico 2 — Sentiment medio per categoria e lingua (heatmap)
# ---------------------------------------------------------------------------

def chart_sentiment_heatmap(df: pd.DataFrame, persona: str, argomento: str | None) -> go.Figure:
    """
    Heatmap: sentiment medio per categoria (y) × lingua (x).

    Input DataFrame atteso: [categoria, lingua, sent_medio, totale]
    """
    if df.empty or "sent_medio" not in df.columns:
        return _empty_figure("Nessun dato disponibile per i filtri selezionati.")

    df = df.copy()
    df["sent_medio"] = df["sent_medio"].astype(float)

    # Pivot: righe = categoria, colonne = lingua
    pivot = df.pivot_table(
        index="categoria",
        columns="lingua",
        values="sent_medio",
        aggfunc="mean",
    )

    pivot_totale = df.pivot_table(
        index="categoria",
        columns="lingua",
        values="totale",
        aggfunc="sum",
    ).reindex(index=pivot.index, columns=pivot.columns)

    # Testo dentro le celle
    cell_text = []
    hover_text = []
    for cat in pivot.index:
        row_cell, row_hover = [], []
        for lang in pivot.columns:
            s = pivot.loc[cat, lang]
            t = pivot_totale.loc[cat, lang]
            if pd.isna(s):
                row_cell.append("N/D")
                row_hover.append("Nessun dato")
            else:
                row_cell.append(f"{s:+.3f}")
                # t può essere NaN se pivot_totale ha combinazioni mancanti
                row_hover.append(f"Sentiment: {s:+.4f}<br>Mention: {int(t) if pd.notna(t) else 0}")
        cell_text.append(row_cell)
        hover_text.append(row_hover)

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[f"  {l}  " for l in pivot.columns.tolist()],   # padding visivo
        y=pivot.index.tolist(),
        text=cell_text,
        texttemplate="%{text}",
        textfont=dict(size=13, color="black"),
        customdata=hover_text,
        hovertemplate="<b>%{y}</b> | Lingua: %{x}<br>%{customdata}<extra></extra>",
        colorscale=[
            [0.0,  "#d73027"],
            [0.5,  "#ffffbf"],
            [1.0,  "#1a9850"],
        ],
        zmid=0,
        zmin=-1,
        zmax=1,
        colorbar=dict(
            title=dict(text="Sentiment", side="right"),
            tickvals=[-1.0, -0.5, 0.0, 0.5, 1.0],
            ticktext=["−1.0<br>Negativo", "−0.5", "0.0<br>Neutro", "+0.5", "+1.0<br>Positivo"],
            len=0.8,
            thickness=18,
        ),
    ))

    subtitle = f" — {argomento}" if argomento else ""
    _base_layout(fig, f"Sentiment per Categoria e Lingua — {persona}{subtitle}")
    fig.update_layout(
        hovermode="closest",
        margin=dict(t=80, b=70, l=130, r=120),
    )
    fig.update_xaxes(
        title_text="Lingua",
        side="bottom",
        ticks="outside",
        ticklen=4,
    )
    fig.update_yaxes(
        title_text="Categoria",
        ticks="outside",
        ticklen=4,
        automargin=True,
    )

    return fig


# ---------------------------------------------------------------------------
# Grafico 3 — Volume di mention nel tempo
# ---------------------------------------------------------------------------

def chart_volume_trend(
    df: pd.DataFrame,
    series: list[str],
    label: str | None,
    series_col: str = "persona",
) -> go.Figure:
    """
    Linechart: volume di mention nel tempo.

    series:     lista dei valori della colonna series_col da mostrare.
    series_col: "persona" o "argomento".
    label:      testo aggiuntivo nel titolo.

    Input DataFrame atteso: [giorno, {series_col}, totale]
    """
    df = df.copy()
    if not df.empty:
        df["giorno"] = pd.to_datetime(df["giorno"])
        df["totale"] = df["totale"].astype(int)

    series_con_dati: set[str] = set(df[series_col].unique()) if not df.empty else set()
    fig = go.Figure()

    for i, serie in enumerate(series):
        color = _COLOR_SEQUENCE[i % len(_COLOR_SEQUENCE)]

        if serie not in series_con_dati:
            fig.add_trace(go.Scatter(
                x=[], y=[], mode="lines",
                name=f"{serie} (nessun dato)",
                line=dict(width=2, color=color, dash="dot"),
                showlegend=True,
            ))
        else:
            subset = df[df[series_col] == serie].sort_values("giorno")
            fig.add_trace(go.Scatter(
                x=subset["giorno"],
                y=subset["totale"],
                name=serie,
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(color=color, size=5),
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Data: %{x|%d %b %Y}<br>"
                    "Mention: %{y:,}<extra></extra>"
                ),
            ))

    subtitle = f" — {label}" if label else ""
    _base_layout(fig, f"Volume Mention nel Tempo{subtitle}")
    legend_title = "Argomento" if series_col == "argomento" else "Persona"
    fig.update_layout(legend_title_text=legend_title)
    fig.update_yaxes(title_text="Totale mention", tickformat=",d", rangemode="tozero")
    if not df.empty:
        fig.update_xaxes(**_date_xaxis(df["giorno"]))
    else:
        fig.update_xaxes(title_text="Data")

    return fig


# ---------------------------------------------------------------------------
# Grafico 4 — Barchart sentiment per categoria (alternativa alla heatmap)
# ---------------------------------------------------------------------------

def chart_posizionamento(
    df: pd.DataFrame,
    label: str | None,
    series_col: str = "persona",
) -> go.Figure:
    """
    Scatter di posizionamento reputazionale:
      X = mention totali (visibilità)
      Y = sentiment medio ponderato (tono)
    Un punto per serie (persona o argomento), diviso in 4 quadranti.

    series_col: colonna che identifica la serie ("persona" o "argomento").
    Input DataFrame atteso: [{series_col}, totale, sent_medio]
    """
    if df.empty or "sent_medio" not in df.columns:
        return _empty_figure("Nessun dato disponibile per i filtri selezionati.")

    df = df.copy().dropna(subset=["sent_medio"])
    df["totale"]     = df["totale"].astype(int)
    df["sent_medio"] = df["sent_medio"].astype(float)

    x_mid = df["totale"].median()

    fig = go.Figure()

    # Linee di quadrante
    fig.add_vline(x=x_mid, line_dash="dot", line_color="#aaaaaa", line_width=1)
    fig.add_hline(y=0,     line_dash="dash", line_color="#888888", line_width=1.2)
    fig.add_hrect(y0=-0.1, y1=0.1, fillcolor="gray", opacity=0.06, line_width=0)

    # Punti
    for i, row in df.iterrows():
        color = _COLOR_SEQUENCE[i % len(_COLOR_SEQUENCE)]
        nome = row[series_col]
        fig.add_trace(go.Scatter(
            x=[row["totale"]],
            y=[row["sent_medio"]],
            mode="markers+text",
            name=nome,
            marker=dict(size=18, color=color, opacity=0.85,
                        line=dict(width=1.5, color="white")),
            text=[nome],
            textposition="top center",
            textfont=dict(size=11),
            hovertemplate=(
                f"<b>{nome}</b><br>"
                "Mention: %{x:,}<br>"
                "Sentiment: %{y:+.3f}<extra></extra>"
            ),
            showlegend=False,
        ))

    # Etichette quadranti
    x_max = df["totale"].max() * 1.1
    for qlabel, x, y, anchor in [
        ("Alta visibilità\npositiva",  x_max, 0.95,  "right"),
        ("Alta visibilità\nnegativa",  x_max, -0.95, "right"),
        ("Bassa visibilità\npositiva", 0,     0.95,  "left"),
        ("Bassa visibilità\nnegativa", 0,     -0.95, "left"),
    ]:
        fig.add_annotation(
            x=x, y=y, text=qlabel,
            showarrow=False,
            font=dict(size=10, color="#aaaaaa"),
            xanchor=anchor, yanchor="top" if y > 0 else "bottom",
            xref="x", yref="y",
        )

    subtitle = f" — {label}" if label else ""
    _base_layout(fig, f"Posizionamento Reputazionale{subtitle}")
    fig.update_xaxes(title_text="Mention totali (visibilità)", rangemode="tozero", tickformat=",d")
    fig.update_yaxes(**_sentiment_yaxis())
    fig.update_layout(hovermode="closest")

    return fig


def chart_sentiment_by_categoria(df: pd.DataFrame, persona: str, argomento: str | None) -> go.Figure:
    """
    Barchart verticale raggruppato: una barra per lingua dentro ogni categoria.
    Asse X = categoria, asse Y = sentiment medio, colori = lingua.

    Più leggibile del barchart orizzontale quando le categorie sono poche (< 10).
    Input DataFrame atteso: [categoria, lingua, sent_medio, totale]
    """
    if df.empty or "sent_medio" not in df.columns:
        return _empty_figure("Nessun dato disponibile per i filtri selezionati.")

    df = df.copy()
    df["sent_medio"] = df["sent_medio"].astype(float)

    # Ordina le categorie per sentiment medio complessivo (dal più negativo al più positivo)
    ordine_categorie = (
        df.groupby("categoria")["sent_medio"].mean()
        .sort_values()
        .index.tolist()
    )
    lingue = sorted(df["lingua"].unique().tolist())

    fig = go.Figure()

    for i, lingua in enumerate(lingue):
        subset = df[df["lingua"] == lingua].copy()
        color = _COLOR_SEQUENCE[i % len(_COLOR_SEQUENCE)]

        fig.add_trace(go.Bar(
            x=subset["categoria"],
            y=subset["sent_medio"],
            name=lingua,
            marker_color=color,
            marker_line=dict(width=0.5, color="white"),
            customdata=subset[["totale"]].values,
            hovertemplate=(
                "<b>%{x}</b> | Lingua: %{fullData.name}<br>"
                "Sentiment: %{y:+.4f}<br>"
                "Mention: %{customdata[0]:,}<extra></extra>"
            ),
        ))

    # Banda neutra ±0.1 e linea dello zero
    fig.add_hrect(y0=-0.1, y1=0.1, fillcolor="gray", opacity=0.07, line_width=0)
    fig.add_hline(y=0, line_dash="dash", line_color="#888888", line_width=1.2)

    subtitle = f" — {argomento}" if argomento else ""
    _base_layout(fig, f"Sentiment per Categoria — {persona}{subtitle}")

    fig.update_layout(
        barmode="group",
        bargap=0.3,
        bargroupgap=0.05,
        hovermode="closest",
        legend_title_text="Lingua",
    )
    fig.update_xaxes(
        title_text="Categoria",
        categoryorder="array",
        categoryarray=ordine_categorie,
        tickfont=dict(size=12, color="#222222"),
        automargin=True,
    )
    fig.update_yaxes(
        **_sentiment_yaxis(),
    )

    return fig
