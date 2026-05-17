FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
COPY mempalace-reference ./mempalace-reference

RUN pip install --no-cache-dir -e ./mempalace-reference -e .

EXPOSE 8000

CMD ["uvicorn", "swigar_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
