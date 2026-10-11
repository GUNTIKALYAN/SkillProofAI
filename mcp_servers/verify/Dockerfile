FROM python:3.10-slim

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app verifymcp ./verifymcp
COPY --chown=app:app tests ./tests
COPY --chown=app:app pytest.ini .

USER app

EXPOSE 8000

CMD ["python", "-m", "verifymcp"]
