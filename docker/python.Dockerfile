FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/aegis

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .

# Least privilege: drop root before serving, and give the app writable
# dirs for Streamlit config + audit log.
RUN useradd -m -u 1000 -d /home/aegis aegis \
    && mkdir -p /var/log/aegis /home/aegis/.streamlit \
    && chown -R aegis:aegis /home/aegis /var/log/aegis

USER aegis
WORKDIR /home/aegis

EXPOSE 8501

CMD ["streamlit", "run", "/app/src/aegis/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
