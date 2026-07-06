# Docker Backup Manager

Nowoczesny, bezpieczny i kontenerowy system do zarządzania kopiami zapasowymi (lokalnymi oraz chmurowymi) dedykowany dla serwerów NAS oraz środowisk Linux. Aplikacja oferuje pełny podgląd logów w czasie rzeczywistym, kolejkowanie zadań zabezpieczające wydajność dyskową (I/O) oraz rozproszoną autoryzację użytkowników.

## 🚀 Architektura i Główne Funkcje

- **Backend (FastAPI):** Zarządza zadaniami, komunikacją z silnikami kopiowania (Rsync/Rclone), kolejkowaniem zadań (ThreadPool z limitem wątków chroniącym dyski przed przeciążeniem) oraz bezpieczeństwem (JWT + bcrypt).
- **Frontend (React + Tailwind CSS + Vite):** Elegancki dashboard z ciemnym motywem, dynamicznym drzewem katalogów NAS, konsolą logów na żywo i stanowym zabezpieczeniem sesji.
- **Baza Danych Flat-File:** Cała konfiguracja zadań oraz użytkowników zapisywana jest atomowo w jednym pliku `config.json`, co eliminuje potrzebę utrzymywania ciężkich baz SQL i ułatwia przenoszenie systemu.

---

## 🏗️ Struktura Projektu

Do uruchomienia lub migracji aplikacji wymagana jest następująca struktura plików w katalogu roboczym:

```text
.
├── docker-compose.yml
├── .env
├── config.json
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt  # Musi zawierać: pyjwt, bcrypt, fastapi, uvicorn, apscheduler
│   └── main.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── Login.tsx
        ├── TaskModal.tsx
        ├── LogModal.tsx
        └── FolderBrowserModal.tsx

```

---

## ⚙️ Wymagania i Konfiguracja Środowiska

### 1. Plik `.env`

Utwórz plik `.env` w katalogu głównym projektu. Zmienne te sterują zachowaniem kontenerów i są automatycznie wstrzykiwane przez demona Docker do kodu źródłowego.

```env
# Domyślne poświadczenia administratora (używane, gdy baza użytkowników w pliku JSON jest pusta)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=TwojeSuperTajneHasloStartowe123!

# Bezpieczeństwo sesji i tokenów JWT
JWT_SECRET=wpisz_tutaj_bardzo_dlugi_losowy_ciag_znakow_alfanumerycznych

# Blokada rejestracji (true = brak możliwości tworzenia kont z poziomu aplikacji)
DISABLE_REGISTRATION=true

# Klucze API (Kompatybilność komunikacji frontend <-> backend)
API_KEY=TwojKluczAPIZabezpieczajacyKomunikacje
VITE_API_KEY=TwojKluczAPIZabezpieczajacyKomunikacje

```

### 2. Plik `config.json` (Baza danych flat-file)

Przed pierwszym uruchomieniem zainicjalizuj strukturę bazy danych. Jeśli przeprowadzasz czystą instalację, plik musi zawierać poprawny obiekt JSON:

```json
{
  "tasks": [],
  "users": []
}

```

*Uwaga: Po zarejestrowaniu użytkownika przez aplikację (gdy `DISABLE_REGISTRATION=false`), jego hasło zostanie automatycznie zapisane w tablicy `users` w formie bezpiecznego hasza bcrypt. Plik ten rośnie wraz z dodawaniem nowych zadań.*

---

## 🏁 Uruchomienie Systemu

W folderze głównym projektu wykonaj w terminalu następujące polecenia, aby skompilować aplikację:

```bash
# 1. Zbudowanie obrazów i uruchomienie kontenerów w tle na czysto
sudo docker compose up -d --build

# 2. Weryfikacja statusu działania procesów
sudo docker compose ps

# 3. Podgląd logów w czasie rzeczywistym w razie problemów startowych
sudo docker compose logs -f backup-backend

```

Aplikacja frontendowa będzie dostępna w przeglądarce pod adresem IP serwera NAS na standardowym porcie HTTP (`http://IP_NAS`).

---

## 📦 Instrukcja Migracji w Inne Miejsce

Dzięki pełnej konteneryzacji przeniesienie systemu na inny serwer NAS lub VPS sprowadza się do 4 kroków:

1. **Kopiowanie plików:** Spakuj i przenieś katalog projektu na nową maszynę (np. za pomocą `scp`, `sftp` lub zewnętrznego nośnika).
2. **Zachowanie lub reset danych:** - Jeśli chcesz przenieść **wszystkie zadania i konta**, przenieś nienaruszony plik `config.json`.
* Jeśli przenosisz zadania, ale chcesz **zresetować zapomniane hasła**, otwórz plik `config.json` na nowej maszynie i wyczyść tablicę użytkowników do postaci `"users": []`. System pozwoli wtedy na ponowne zalogowanie się danymi startowymi z pliku `.env`.


3. **Dostosowanie ścieżek:** Otwórz `docker-compose.yml` na nowym serwerze i zaktualizuj sekcję `volumes` (mapowanie folderów źródłowych `/storage` oraz docelowych), dostosowując je do punktów montowania dysków na nowej maszynie.
4. **Rozruch:** Wykonaj `sudo docker compose down && sudo docker compose up -d --build`. System od razu zainstaluje wymagane pakiety kryptograficzne w kontenerze i podniesie panel zabezpieczony hasłem.
