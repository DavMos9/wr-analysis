FROM python:3.11-slim

WORKDIR /app

# curl necessario per l'healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dipendenze Python — copiate prima del codice per sfruttare il cache layer Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codice sorgente del dashboard.
COPY app.py charts.py config.py db.py .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.baseUrlPath=/dashboard", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
