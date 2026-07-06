FROM node:20-alpine

WORKDIR /app

# Kopiujemy plik z listą paczek
COPY package.json ./

# Instalujemy zależności (Vite, React, Lucide itp.) wewnątrz kontenera
RUN npm install

# Kopiujemy resztę kodu źródłowego (src, index.html, vite.config.ts)
COPY . .

EXPOSE 5173

# Uruchamiamy serwer deweloperski Vite
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]