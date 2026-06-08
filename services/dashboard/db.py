"""
db.py
-----
Gestisce la connessione a PostgreSQL e le query sulla tabella wr_sent_giorno.
Ogni funzione ritorna un pandas DataFrame pronto per la visualizzazione.

Responsabilità:
- Connessione (con context manager per chiusura sicura)
- Query parametrizzate (nessun SQL costruito con f-string)
- Logging degli errori senza propagare dettagli sensibili all'UI
"""

import logging
from contextlib import contextmanager
from datetime import date
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.extras

from config import DB_CONFIG

logger = logging.getLogger(__name__)

TABLE = "wr_sent_giorno"


@contextmanager
def _get_connection():
    """Context manager per la connessione al DB. Chiude sempre la connessione."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Connessione al database stabilita.")
        yield conn
    except psycopg2.OperationalError as e:
        logger.error("Impossibile connettersi al database: %s", e)
        raise
    finally:
        if conn and not conn.closed:
            conn.close()
            logger.info("Connessione al database chiusa.")


def _query_to_df(sql: str, params: tuple) -> pd.DataFrame:
    """Esegue una query parametrizzata e ritorna un DataFrame."""
    with _get_connection() as conn:
        try:
            df = pd.read_sql_query(sql, conn, params=params)
            logger.info("Query eseguita: %d righe restituite.", len(df))
            return df
        except Exception as e:
            logger.error("Errore durante l'esecuzione della query: %s", e)
            raise


# ---------------------------------------------------------------------------
# Funzioni di lookup (per popolare i filtri nell'UI)
# ---------------------------------------------------------------------------

def get_argomenti() -> list[str]:
    """Ritorna la lista distinta di argomenti presenti nel DB."""
    sql = f"SELECT DISTINCT argomento FROM {TABLE} ORDER BY argomento"
    df = _query_to_df(sql, ())
    return df["argomento"].tolist()


def get_target(argomenti: Optional[list[str]] = None) -> list[str]:
    """
    Ritorna i target che hanno dati per almeno uno degli argomenti selezionati.
    Se un target ha dati per più argomenti selezionati appare una sola volta (DISTINCT).
    None o lista vuota = tutti i target.
    """
    if argomenti:
        placeholders = ", ".join(["%s"] * len(argomenti))
        sql = f"SELECT DISTINCT persona FROM {TABLE} WHERE argomento IN ({placeholders}) ORDER BY persona"
        df = _query_to_df(sql, tuple(argomenti))
    else:
        sql = f"SELECT DISTINCT persona FROM {TABLE} ORDER BY persona"
        df = _query_to_df(sql, ())
    return df["persona"].tolist()


def get_date_range() -> tuple[date, date]:
    """
    Ritorna la data minima e massima disponibili nel DB.
    Se la tabella è vuota (MIN/MAX ritornano NULL), usa un range di default
    degli ultimi 30 giorni per non far crashare i widget st.date_input.
    """
    from datetime import timedelta
    sql = f"SELECT MIN(giorno) AS min_date, MAX(giorno) AS max_date FROM {TABLE}"
    df = _query_to_df(sql, ())
    min_date = df["min_date"].iloc[0]
    max_date = df["max_date"].iloc[0]
    if min_date is None or max_date is None:
        today = date.today()
        return today - timedelta(days=30), today
    return min_date, max_date


def get_kpi(
    persone: list[str],
    argomenti: Optional[list[str]],
    data_inizio: date,
    data_fine: date,
) -> dict:
    """
    Restituisce i KPI aggregati per il gruppo di target selezionati:
    mention totali, sentiment medio ponderato, giorno migliore/peggiore,
    canale dominante per volume.
    """
    if not persone:
        return {}

    placeholders = ", ".join(["%s"] * len(persone))
    base = f"persona IN ({placeholders}) AND giorno BETWEEN %s AND %s"
    params: tuple = tuple(persone) + (data_inizio, data_fine)
    arg_clause, params = _argomenti_clause(argomenti, params)
    base += arg_clause

    # Totale mention e sentiment medio
    df_agg = _query_to_df(f"""
        SELECT
            SUM(totale) AS total_mentions,
            SUM(sent_medio * totale) / NULLIF(SUM(totale), 0) AS avg_sentiment
        FROM {TABLE} WHERE {base}
    """, params)

    # Giorno migliore e peggiore (sentiment ponderato per giorno)
    df_days = _query_to_df(f"""
        SELECT giorno,
               SUM(sent_medio * totale) / NULLIF(SUM(totale), 0) AS sent_g
        FROM {TABLE} WHERE {base}
        GROUP BY giorno HAVING SUM(totale) > 0
        ORDER BY sent_g
    """, params)

    # Canale dominante per volume
    df_cat = _query_to_df(f"""
        SELECT categoria, SUM(totale) AS tot
        FROM {TABLE} WHERE {base}
        GROUP BY categoria ORDER BY tot DESC LIMIT 1
    """, params)

    result: dict = {
        "total_mentions": int(df_agg["total_mentions"].iloc[0] or 0),
        "avg_sentiment":  float(df_agg["avg_sentiment"].iloc[0]) if df_agg["avg_sentiment"].iloc[0] is not None else None,
        "best_day":       str(df_days["giorno"].iloc[-1]) if not df_days.empty else None,
        "worst_day":      str(df_days["giorno"].iloc[0])  if not df_days.empty else None,
        "top_categoria":  df_cat["categoria"].iloc[0]      if not df_cat.empty else None,
    }
    return result


def get_posizionamento(
    persone: list[str],
    argomenti: Optional[list[str]],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """
    Per ogni target: mention totali e sentiment medio ponderato.
    Usato per il grafico di posizionamento (scatter).
    Ritorna colonne: persona, totale, sent_medio
    """
    if not persone:
        return pd.DataFrame()

    placeholders = ", ".join(["%s"] * len(persone))
    base = f"persona IN ({placeholders}) AND giorno BETWEEN %s AND %s"
    params: tuple = tuple(persone) + (data_inizio, data_fine)
    arg_clause, params = _argomenti_clause(argomenti, params)
    base += arg_clause

    return _query_to_df(f"""
        SELECT
            persona,
            SUM(totale) AS totale,
            SUM(sent_medio * totale) / NULLIF(SUM(totale), 0) AS sent_medio
        FROM {TABLE}
        WHERE {base}
        GROUP BY persona
        ORDER BY persona
    """, params)


# ---------------------------------------------------------------------------
# Query "by argomento" — usate quando 1 target, N argomenti selezionati
# La serie è l'argomento anziché la persona.
# ---------------------------------------------------------------------------

def get_sentiment_trend_by_argomento(
    persona: str,
    argomenti: list[str],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """Trend sentiment per argomento (serie = argomento). Ritorna: giorno, argomento, sent_medio, totale"""
    placeholders = ", ".join(["%s"] * len(argomenti))
    return _query_to_df(f"""
        SELECT giorno, argomento,
               SUM(totale) AS totale,
               SUM(sent_medio * totale) / NULLIF(SUM(totale), 0) AS sent_medio
        FROM {TABLE}
        WHERE persona = %s AND argomento IN ({placeholders}) AND giorno BETWEEN %s AND %s
        GROUP BY giorno, argomento
        ORDER BY giorno, argomento
    """, (persona,) + tuple(argomenti) + (data_inizio, data_fine))


def get_volume_trend_by_argomento(
    persona: str,
    argomenti: list[str],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """Volume mention per argomento. Ritorna: giorno, argomento, totale"""
    placeholders = ", ".join(["%s"] * len(argomenti))
    return _query_to_df(f"""
        SELECT giorno, argomento, SUM(totale) AS totale
        FROM {TABLE}
        WHERE persona = %s AND argomento IN ({placeholders}) AND giorno BETWEEN %s AND %s
        GROUP BY giorno, argomento
        ORDER BY giorno, argomento
    """, (persona,) + tuple(argomenti) + (data_inizio, data_fine))


def get_posizionamento_by_argomento(
    persona: str,
    argomenti: list[str],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """Posizionamento per argomento (serie = argomento). Ritorna: argomento, totale, sent_medio"""
    placeholders = ", ".join(["%s"] * len(argomenti))
    return _query_to_df(f"""
        SELECT argomento,
               SUM(totale) AS totale,
               SUM(sent_medio * totale) / NULLIF(SUM(totale), 0) AS sent_medio
        FROM {TABLE}
        WHERE persona = %s AND argomento IN ({placeholders}) AND giorno BETWEEN %s AND %s
        GROUP BY argomento
        ORDER BY argomento
    """, (persona,) + tuple(argomenti) + (data_inizio, data_fine))


# ---------------------------------------------------------------------------
# Query per i grafici
# ---------------------------------------------------------------------------

def _argomenti_clause(argomenti: Optional[list[str]], params: tuple) -> tuple[str, tuple]:
    """
    Costruisce la clausola SQL e i parametri per il filtro su argomento.
    - argomenti None o lista vuota → nessun filtro (tutti gli argomenti)
    - lista con 1+ elementi → AND argomento IN (%s, %s, ...)
    Ritorna (clausola_sql, params_aggiornati).
    """
    if not argomenti:
        return "", params
    placeholders = ", ".join(["%s"] * len(argomenti))
    return f" AND argomento IN ({placeholders})", params + tuple(argomenti)


def get_sentiment_trend(
    persone: list[str],
    argomenti: Optional[list[str]],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """
    Trend temporale del sentiment medio per persona nel range di date.

    argomenti: lista di argomenti da includere. None o [] = tutti.
    Ritorna colonne: giorno, persona, sent_medio, totale
    """
    if not persone:
        return pd.DataFrame()

    placeholders = ", ".join(["%s"] * len(persone))
    base_conditions = f"persona IN ({placeholders}) AND giorno BETWEEN %s AND %s"
    params = tuple(persone) + (data_inizio, data_fine)

    arg_clause, params = _argomenti_clause(argomenti, params)
    base_conditions += arg_clause

    sql = f"""
        SELECT
            giorno,
            persona,
            SUM(totale) AS totale,
            CASE
                WHEN SUM(totale) = 0 THEN NULL
                ELSE SUM(sent_medio * totale) / NULLIF(SUM(totale), 0)
            END AS sent_medio
        FROM {TABLE}
        WHERE {base_conditions}
        GROUP BY giorno, persona
        ORDER BY giorno, persona
    """
    return _query_to_df(sql, params)


def get_sentiment_per_categoria_lingua(
    persona: str,
    argomenti: Optional[list[str]],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """
    Sentiment medio per categoria e lingua per una persona.

    argomenti: lista di argomenti da includere. None o [] = tutti.
    Ritorna colonne: categoria, lingua, sent_medio, totale
    """
    base_conditions = "persona = %s AND giorno BETWEEN %s AND %s"
    params: tuple = (persona, data_inizio, data_fine)

    arg_clause, params = _argomenti_clause(argomenti, params)
    base_conditions += arg_clause

    sql = f"""
        SELECT
            categoria,
            lingua,
            SUM(totale) AS totale,
            CASE
                WHEN SUM(totale) = 0 THEN NULL
                ELSE SUM(sent_medio * totale) / NULLIF(SUM(totale), 0)
            END AS sent_medio
        FROM {TABLE}
        WHERE {base_conditions}
        GROUP BY categoria, lingua
        ORDER BY categoria, lingua
    """
    return _query_to_df(sql, params)


def get_volume_trend(
    persone: list[str],
    argomenti: Optional[list[str]],
    data_inizio: date,
    data_fine: date,
) -> pd.DataFrame:
    """
    Volume di mention totali per persona nel range di date.

    argomenti: lista di argomenti da includere. None o [] = tutti.
    Ritorna colonne: giorno, persona, totale
    """
    if not persone:
        return pd.DataFrame()

    placeholders = ", ".join(["%s"] * len(persone))
    base_conditions = f"persona IN ({placeholders}) AND giorno BETWEEN %s AND %s"
    params = tuple(persone) + (data_inizio, data_fine)

    arg_clause, params = _argomenti_clause(argomenti, params)
    base_conditions += arg_clause

    sql = f"""
        SELECT
            giorno,
            persona,
            SUM(totale) AS totale
        FROM {TABLE}
        WHERE {base_conditions}
        GROUP BY giorno, persona
        ORDER BY giorno, persona
    """
    return _query_to_df(sql, params)
