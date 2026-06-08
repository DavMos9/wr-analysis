"""
config.py
---------
Carica le credenziali del database da un file .env e le espone
come dizionario DB_CONFIG, utilizzato da db.py per la connessione.

Il file .env deve trovarsi nella stessa directory di questo script.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carica il .env dalla directory del progetto
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _require(key: str) -> str:
    """Legge una variabile d'ambiente obbligatoria; lancia errore se assente."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Variabile d'ambiente '{key}' non trovata. "
            f"Verifica che il file .env esista e contenga questa chiave."
        )
    return value


DB_CONFIG: dict = {
    "host":     _require("DB_HOST"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   _require("DB_NAME"),
    "user":     _require("DB_USER"),
    "password": _require("DB_PASSWORD"),
}
