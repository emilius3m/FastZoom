FROM python:3.12
WORKDIR /app

# PYTHONPATH come ENV garantisce che ogni processo figlio (incluso il worker
# del reloader uvicorn --reload) trovi sempre il modulo app.app senza errori.
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]