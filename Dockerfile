FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY stock_analysis ./stock_analysis

EXPOSE 8000

CMD ["uv", "run", "python", "stock_analysis/manage.py", "runserver", "0.0.0.0:8000"]
