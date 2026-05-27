FROM python:3.11-slim

WORKDIR /app

# Dipendenze di sistema
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

# Dipendenze Python del servizio
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Il core della pipeline (wr-analysis-light) viene montato a /app/core
# tramite bind-mount in docker-compose — non copiato nell'immagine.
# Questo permette di sviluppare il core senza ricostruire l'immagine.

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
