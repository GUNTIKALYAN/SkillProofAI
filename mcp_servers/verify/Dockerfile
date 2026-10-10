FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY verifymcp ./verifymcp
COPY tests ./tests
COPY pytest.ini .

EXPOSE 8000

CMD ["python", "-m", "verifymcp"]
