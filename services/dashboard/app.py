"""
app.py
------
Interfaccia Streamlit per la Web Reputational Analysis.
Orchestrazione: UI → db.py (dati) → charts.py (grafici).

Avvio: streamlit run app.py
"""

import logging

import streamlit as st

import charts
import db

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ---------------------------------------------------------------------------
# Configurazione pagina
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="WR Sentiment Analysis",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Web Reputational Analysis — Sentiment Dashboard")
st.caption("Analisi del sentiment per persona, categoria e lingua nel tempo.")

# ---------------------------------------------------------------------------
# Caricamento dati di lookup (cached per non riqueryare ad ogni interazione)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner="Caricamento dati dal database...")
def load_lookup_data():
    argomenti = db.get_argomenti()
    date_min, date_max = db.get_date_range()
    return argomenti, date_min, date_max


@st.cache_data(ttl=300)
def load_target(argomenti: tuple | None) -> list[str]:
    # tuple per compatibilità con st.cache_data (le liste non sono hashable)
    return db.get_target(list(argomenti) if argomenti else None)


try:
    argomenti_disponibili, date_min, date_max = load_lookup_data()
except Exception as e:
    st.error(f"❌ Impossibile connettersi al database. Controlla il file `.env`.\n\nDettaglio: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — Filtri globali
# ---------------------------------------------------------------------------

st.sidebar.link_button("◀ Pipeline", "/", use_container_width=True)
st.sidebar.divider()

st.sidebar.header("Filtri")

# Tipo di grafico
tipo_grafico = st.sidebar.selectbox(
    "Tipo di grafico",
    options=[
        "Trend Sentiment nel Tempo",
        "Volume Mention nel Tempo",
        "Posizionamento Reputazionale",
    ],
)

st.sidebar.divider()

# 1. Argomento — multiselect, determina i target disponibili
argomento_sel: list[str] = st.sidebar.multiselect(
    "Argomento",
    options=argomenti_disponibili,
    default=[],
    placeholder="Tutti (nessun filtro)",
    help="Seleziona uno o più argomenti. Vuoto = mostra tutti i target.",
)
# Lista vuota = nessun filtro; lista piena = filtra per quelli selezionati
argomento_filtro: list[str] | None = argomento_sel if argomento_sel else None
argomento_label: str | None = ", ".join(argomento_sel) if argomento_sel else None

# 2. Target — mostra solo quelli con dati per almeno uno degli argomenti selezionati
target_disponibili = load_target(tuple(argomento_filtro) if argomento_filtro else None)

# Posizionamento usa sempre multi-target (confronto ha senso con più target)
is_multi_target = tipo_grafico in (
    "Trend Sentiment nel Tempo",
    "Volume Mention nel Tempo",
    "Posizionamento Reputazionale",
)

if is_multi_target:
    persone_selezionate = st.sidebar.multiselect(
        "Target (confronto)",
        options=target_disponibili,
        default=target_disponibili if tipo_grafico == "Posizionamento Reputazionale"
                else target_disponibili[:1],
        help="Seleziona uno o più target da confrontare.",
    )
    persona_singola = persone_selezionate[0] if persone_selezionate else None
else:
    persona_singola = st.sidebar.selectbox(
        "Target",
        options=target_disponibili if target_disponibili else ["—"],
    )
    persona_singola = persona_singola if persona_singola != "—" else None
    persone_selezionate = [persona_singola] if persona_singola else []

# argomento_filtro è già una lista o None — usato direttamente nelle query
argomenti_query: list[str] | None = argomento_filtro

st.sidebar.divider()

# Range di date
col1, col2 = st.sidebar.columns(2)
with col1:
    data_inizio = st.date_input("Da", value=date_min, min_value=date_min, max_value=date_max)
with col2:
    data_fine = st.date_input("A", value=date_max, min_value=date_min, max_value=date_max)

if data_inizio > data_fine:
    st.sidebar.error("La data di inizio deve essere precedente alla data di fine.")
    st.stop()

# ---------------------------------------------------------------------------
# Corpo principale
# ---------------------------------------------------------------------------

if not persone_selezionate:
    st.info("Seleziona almeno un target dalla sidebar per visualizzare il grafico.")
    st.stop()

# KPI Panel — layout differente in base al numero di target selezionati
with st.spinner("Caricamento KPI..."):
    try:
        kpi = db.get_kpi(persone_selezionate, argomento_filtro, data_inizio, data_fine)
        df_kpi_per_target = db.get_posizionamento(
            persone_selezionate, argomento_filtro, data_inizio, data_fine
        )
    except Exception as e:
        kpi = {}
        df_kpi_per_target = None
        st.warning(f"KPI non disponibili: {e}")

if kpi:
    is_single = len(persone_selezionate) == 1

    if is_single:
        # Singolo target: tutti i KPI hanno significato pieno
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("📊 Mention totali",   f"{kpi['total_mentions']:,}")
        sent = kpi.get("avg_sentiment")
        c2.metric("💬 Sentiment medio",  f"{sent:+.3f}" if sent is not None else "N/D")
        c3.metric("📅 Giorno migliore",  kpi.get("best_day")      or "N/D")
        c4.metric("📅 Giorno peggiore",  kpi.get("worst_day")     or "N/D")
        c5.metric("📰 Canale dominante", kpi.get("top_categoria") or "N/D")
    else:
        # Multi-target: aggregati che hanno senso + sentiment individuale per target
        c1, c2 = st.columns(2)
        c1.metric("📊 Mention totali (gruppo)",   f"{kpi['total_mentions']:,}")
        c2.metric("📰 Canale dominante (gruppo)", kpi.get("top_categoria") or "N/D")

        if df_kpi_per_target is not None and not df_kpi_per_target.empty:
            st.caption("💬 Sentiment medio per target")
            n = len(df_kpi_per_target)
            cols = st.columns(min(n, 5))  # max 5 colonne per riga
            for idx, (_, row) in enumerate(df_kpi_per_target.iterrows()):
                col = cols[idx % 5]
                s = row["sent_medio"]
                col.metric(
                    row["persona"],
                    f"{s:+.3f}" if s is not None else "N/D",
                    help=f"Mention: {int(row['totale']):,}",
                )

    st.divider()

# Modalità confronto: 1 target + N argomenti → serie per argomento
compare_by_topic = (
    len(persone_selezionate) == 1
    and argomento_filtro is not None
    and len(argomento_filtro) > 1
)
target_singolo = persone_selezionate[0] if compare_by_topic else None

# Grafico principale
with st.spinner("Caricamento dati in corso..."):
    try:
        if tipo_grafico == "Trend Sentiment nel Tempo":
            if compare_by_topic:
                # Serie = argomento, label = nome del target
                df  = db.get_sentiment_trend_by_argomento(target_singolo, argomento_filtro, data_inizio, data_fine)
                fig = charts.chart_sentiment_trend(df, argomento_filtro, target_singolo, series_col="argomento")
            else:
                df  = db.get_sentiment_trend(persone_selezionate, argomenti_query, data_inizio, data_fine)
                fig = charts.chart_sentiment_trend(df, persone_selezionate, argomento_label)

        elif tipo_grafico == "Volume Mention nel Tempo":
            if compare_by_topic:
                df  = db.get_volume_trend_by_argomento(target_singolo, argomento_filtro, data_inizio, data_fine)
                fig = charts.chart_volume_trend(df, argomento_filtro, target_singolo, series_col="argomento")
            else:
                df  = db.get_volume_trend(persone_selezionate, argomenti_query, data_inizio, data_fine)
                fig = charts.chart_volume_trend(df, persone_selezionate, argomento_label)

        elif tipo_grafico == "Posizionamento Reputazionale":
            if compare_by_topic:
                df  = db.get_posizionamento_by_argomento(target_singolo, argomento_filtro, data_inizio, data_fine)
                fig = charts.chart_posizionamento(df, target_singolo, series_col="argomento")
            else:
                df  = db.get_posizionamento(persone_selezionate, argomento_filtro, data_inizio, data_fine)
                fig = charts.chart_posizionamento(df, argomento_label)

        else:
            raise ValueError(f"Tipo di grafico non gestito: {tipo_grafico!r}")

    except Exception as e:
        st.error(f"❌ Errore durante il recupero dei dati: {e}")
        st.stop()

st.plotly_chart(fig, use_container_width=True)

with st.expander("📋 Dati grezzi della query"):
    if df.empty:
        st.write("Nessun dato disponibile per i filtri selezionati.")
    else:
        st.dataframe(df, use_container_width=True)
        st.caption(f"{len(df)} righe restituite.")
