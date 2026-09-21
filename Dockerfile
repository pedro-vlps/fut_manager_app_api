FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.3.3

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root && \
    pip install --no-cache-dir "uvicorn[standard]"

COPY src ./src

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.__main__:app", "--host", "0.0.0.0", "--port", "8000"]
