FROM python:3.11-slim

# Wyciszenie debconf oraz pip
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Instalacja rsync, curl, unzip oraz oficjalnego rclone
RUN apt-get update && apt-get install -y rsync curl unzip && \
    curl https://rclone.org/install.sh | bash && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalacja zależności z requirements.txt (w warstwie cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiowanie reszty kodu backendu
COPY . .

# Uruchomienie serwera FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
