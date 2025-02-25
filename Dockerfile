FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e .

COPY . /app/

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
