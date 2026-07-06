FROM python:3.11-slim

# Instalujemy rsync oraz rclone w systemie kontenera
RUN apt-get update && apt-get install -y rsync rclone && rm -rf /var/lib/apt/lists/*

# Instalujemy wymagane biblioteki Pythona (dodany apscheduler)
RUN pip install --no-cache-dir fastapi uvicorn apscheduler

# Ustalamy folder roboczy wewnątrz kontenera
WORKDIR /app

# Uruchamiamy serwer z automatycznym przeładowaniem kodu
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "."]