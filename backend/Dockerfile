FROM python:3.11-slim

# Wyłączenie interaktywnych monitów debconf oraz wyciszenie spamu z pip
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

ENV NPM_CONFIG_LOGLEVEL=warn

# Instalujemy rsync oraz rclone w systemie kontenera
#RUN apt-get update && apt-get install -y rsync rclone && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y rsync curl unzip && \
    curl https://rclone.org/install.sh | bash && \
    rm -rf /var/lib/apt/lists/*

# Instalujemy wymagane biblioteki Pythona (dodany apscheduler)
RUN pip install --no-cache-dir fastapi uvicorn apscheduler

# Ustalamy folder roboczy wewnątrz kontenera
WORKDIR /app

# Uruchamiamy serwer z automatycznym przeładowaniem kodu
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "."]