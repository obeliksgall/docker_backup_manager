# Docker Backup Manager

Nowoczesny, bezpieczny i w pełni kontenerowy system do zarządzania kopiami zapasowymi (lokalnymi oraz chmurowymi), dedykowany dla serwerów NAS oraz środowisk Linux. Aplikacja oferuje pełny podgląd postępu i prędkości transferu w czasie rzeczywistym, wizualny kreator harmonogramów Cron, kolejkowanie zadań zabezpieczające wydajność dyskową (I/O), łańcuchowanie potoków (pipelines), powiadomienia (Discord / ntfy / E-mail SMTP) oraz rozproszoną autoryzację użytkowników — w lekkiej i niezawodnej architekturze flat-file.

Pisany z pomocą AI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Spis treści

1. [Architektura i główne funkcje](#-architektura-i-główne-funkcje)
2. [Struktura projektu](#️-struktura-projektu)
3. [Wymagania wstępne](#-wymagania-wstępne)
4. [Konfiguracja środowiska](#️-wymagania-i-konfiguracja-środowiska)
   - [.env](#1-plik-env)
   - [config.json oraz config.json.example](#2-plik-configjson-i-configjsonexample)
   - [rclone.conf](#3-plik-rcloneconf)
   - [frontend/env.example](#4-plik-envexample-frontend)
5. [Uruchomienie systemu](#-uruchomienie-systemu)
6. [Korzystanie z aplikacji](#-korzystanie-z-aplikacji)
7. [Wizualny Kreator Cron i harmonogramowanie](#-wizualny-kreator-cron-i-harmonogramowanie)
8. [Podgląd postępu i transferu w czasie rzeczywistym](#-podgląd-postępu-i-transferu-w-czasie-rzeczywistym)
9. [Tryby kopiowania (`mode`)](#-tryby-kopiowania-mode)
10. [Łańcuchowanie zadań (`next_task_id`)](#-łańcuchowanie-zadań-next_task_id)
11. [Retencja i kosz](#️-retencja-i-kosz)
12. [Powiadomienia (Discord, ntfy, E-mail SMTP)](#-powiadomienia)
13. [Referencja API](#-referencja-api)
14. [Bezpieczeństwo](#-bezpieczeństwo)
15. [Instrukcja migracji w inne miejsce](#-instrukcja-migracji-w-inne-miejsce)
16. [Rozwiązywanie problemów](#-rozwiązywanie-problemów)
17. [Znane ograniczenia](#️-znane-ograniczenia)
18. [Licencja](#-licencja)

---

## 🚀 Architektura i Główne Funkcje

- **Backend (FastAPI, Python 3.11):** 
  - Bezpośrednia integracja z silnikami kopiowania: `rsync` dla kopii lokalnych oraz `rclone` dla zdalnych chmur.
  - Kolejkowanie zadań oparte na APScheduler z `ThreadPoolExecutor(max_workers=1)`, co serializuje operacje I/O i chroni dyski NAS przed przegrzaniem i przeciążeniem.
  - Parsowanie transferu w locie (`--info=progress2` w rsync oraz `--stats=1s` w rclone) ze streamingiem postępu do frontendu.
  - Pełne zabezpieczenie API: JWT (Argon2id / bcrypt) + statyczny klucz `X-API-Key`.
- **Frontend (React 19 + TypeScript + Tailwind CSS + Vite):**
  - Responsywny dashboard z ciemnym motywem, kartami zadań, przyciskami natychmiastowego startu i zatrzymania (STOP).
  - Dynamiczny pasek postępu transferu na żywo (procent %, prędkość MiB/s, licznik przetransferowanych plików, czas ETA).
  - Wbudowany **Wizualny Kreator Crona** z gotowymi presetami (Codziennie, Co godzinę, Interwał co X godzin, Dni robocze, Tylko ręcznie) oraz podglądem słownym w języku polskim.
  - Wbudowana bezpieczna przeglądarka podkatalogów serwera NAS (wybór ścieżek źródła i celu jednym kliknięciem).
  - Podgląd logów w czasie rzeczywistym z automatycznym odświeżaniem.
  - Pełne wsparcie dwujęzyczne PL/EN (i18next).
- **Lekka baza danych Flat-File (`config.json`):**
  - Całość konfiguracji zadań, ustawień globalnych i użytkowników przechowywana w czytelnym pliku JSON.
  - Walidacja schematem `config.schema.json` oraz odporność na brakujące pola i uszkodzenia.
  - Dostępny wzorcowy plik `config.json.example`.
- **Łańcuchowanie zadań (Pipelines):** Każde zadanie może automatycznie uruchamiać kolejne zadanie po pomyślnym zakończeniu (np. Kopia lokalna -> Kopia do chmury).
- **Zarządzanie wersjami i kosz:** Przy trybie `mirror` pliki usuwane z folderu źródłowego trafiają do datowanego katalogu `<destination>-trash/YYYY-MM-DD/`, a zadanie nocne automatycznie czyści wersje starsze niż `retention_days`.
- **Bezpieczne przywracanie danych (Restore):** Zabezpieczenie `restore_enabled` chroni przed przypadkowym nadpisaniem danych produkcyjnych.
- **Wielokanałowe powiadomienia:** Discord Webhook, ntfy.sh (push na telefon) oraz poczta E-mail (SMTP) z filtrowaniem poziomu zdarzeń.

---

## 🏗️ Struktura Projektu

```text
.
├── docker-compose.yml
├── .env                        # Konfiguracja środowiska (kopiowana z .env.example)
├── .env.example                # Szablon zmiennych środowiskowych
├── config.json.example         # Przykładowy wzorcowy plik konfiguracji zadań
├── LICENSE
├── README.md                   # Niniejsza dokumentacja
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt        # fastapi, uvicorn, apscheduler, pyjwt, bcrypt, python-multipart
│   ├── main.py                 # Główna aplikacja FastAPI (silnik backupu, scheduler, API)
│   ├── main_EN.py              # Alternatywny plik z komunikatami w języku angielskim
│   ├── i18n.py                 # Tłumaczenia backendu
│   ├── config/
│   │   ├── config.json         # Aktywna konfiguracja zadań i użytkowników
│   │   ├── config.json.example # Wzorcowa konfiguracja
│   │   ├── config.schema.json  # Schemat JSON Schema do walidacji struktury
│   │   └── rclone.conf         # Konfiguracja zdalnych dysków chmurowych (remotes)
│   └── logs/                   # Generowane w trakcie pracy logi operacji
│       ├── app.log
│       └── tasks/<slug-zadania>/<timestamp>.log
└── frontend/
    ├── Dockerfile
    ├── Dockerfile.prod         # Produkcyjny wieloetapowy obraz z serwerem Nginx
    ├── nginx.conf              # Konfiguracja reverse proxy dla środowiska produkcyjnego
    ├── package.json
    ├── vite.config.ts
    ├── env.example
    └── src/
        ├── main.tsx            # Punkt wejścia React
        ├── App.tsx             # Główny pulpit aplikacji z kartami zadań i pollingiem
        ├── Login.tsx           # Ekran uwierzytelniania JWT
        ├── TaskModal.tsx       # Okno dialogowe tworzenia i edycji zadania
        ├── CronBuilder.tsx     # Wizualny kreator harmonogramów Cron z presetami
        ├── FolderBrowserModal.tsx # Przeglądarka drzewa katalogów /storage
        ├── LogModal.tsx        # Konsola podglądu ostatnich linii logu
        ├── ConfigModal.tsx     # Podgląd i edycja konfiguracji
        └── i18n.ts             # Słowniki i konfiguracja i18next (PL / EN)
```

---

## ✅ Wymagania Wstępne

1. Zainstalowany **Docker** oraz wtyczka **Docker Compose v2** (`docker compose version`).
2. Przypisane uprawnienia odczytu i zapisu do katalogów przeznaczonych na kopie zapasowe.
3. Skonfigurowane zdalne dyski w `backend/config/rclone.conf`, jeśli używane będą zadania typu `cloud` (np. Google Drive, OneDrive, S3, Nextcloud).
4. Otwarte porty sieciowe:
   - `5173` (Frontend w trybie developerskim) lub `80` (wersja produkcyjna Nginx),
   - `8000` (Backend API FastAPI).

---

## ⚙️ Wymagania i Konfiguracja Środowiska

### 1. Plik `.env`

Skopiuj plik szablonu `.env.example` do `.env` w katalogu głównym:

```bash
cp .env.example .env
```

Zawartość pliku `.env`:

```env
# ==========================================
# DOCKER BACKUP MANAGER - KONFIGURACJA (.env)
# ==========================================

# 1. Strefa czasowa i język
TZ=Europe/Warsaw
APP_LANG=pl # pl (polski) lub en (angielski) dla logów i powiadomień

# 2. Bezpieczeństwo i uwierzytelnianie
# Wbudowane konto administratora (zawsze aktywne)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ZmienToSuperHaslo123!

# Zablokowanie otwartej rejestracji nowych kont (zalecane: true)
DISABLE_REGISTRATION=true

# Sekretny klucz do podpisywania tokenów JWT (wygeneruj: openssl rand -hex 32)
JWT_SECRET=zmien-mnie-na-dlugi-losowy-ciag-znakow-32-bajty

# Opcjonalny stały klucz API (używany przez zewnętrzne skrypty / Home Assistant)
API_KEY=TwojKluczAPIZabezpieczajacyKomunikacje

# 3. Konfiguracja powiadomień E-mail (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=twoj-email@gmail.com
SMTP_PASS=twoje-haslo-aplikacji-smtp

# 4. Opcjonalny adres URL backendu (np. przy własnym Reverse Proxy z domeną i HTTPS)
VITE_API_URL=
```

---

### 2. Plik `config.json` i `config.json.example`

Konfiguracja systemu jest przechowywana w `backend/config/config.json`. Do dyspozycji masz gotowy szablon `backend/config/config.json.example` (oraz w katalogu głównym projektu `config.json.example`).

Jeżeli zaczynasz od zera, skopiuj przykład:
```bash
cp backend/config/config.json.example backend/config/config.json
```

#### Szczegółowy opis wszystkich pól w `config.json`:

| Sekcja / Klucz | Typ | Wymagane | Domyślnie | Opis |
| :--- | :--- | :---: | :---: | :--- |
| **`settings.rclone_flags`** | array | Tak | `[]` | Globalne flagi przekazywane do każdego polecenia rclone (np. `--buffer-size=64M`, `--transfers=4`, `--checkers=8`). |
| **`tasks[].id`** | int | Tak | - | Unikalny identyfikator numeryczny zadania. |
| **`tasks[].name`** | string | Tak | - | Przyjazna nazwa wyświetlana w panelu oraz w powiadomieniach. |
| **`tasks[].source`** | string | Tak | - | Ścieżka źródłowa w kontenerze (np. `/storage/documents`). |
| **`tasks[].destination`** | string | Tak | - | Ścieżka docelowa lokalna lub zdalny magazyn chmurowy (np. `gdrive:/backups/documents`). |
| **`tasks[].type`** | string | Tak | `"local"` | Silnik transferu: `"local"` (używa `rsync`) lub `"cloud"` (używa `rclone`). |
| **`tasks[].mode`** | string | Tak | `"copy"` | Tryb synchronizacji: `"mirror"` (lustro z usuwaniem nadmiarowych plików), `"copy"` (kopiowanie nowych/zmienionych) lub `"move"` (przenoszenie). |
| **`tasks[].schedule`** | string | Tak | `""` | 5-polowe wyrażenie Cron (np. `0 2 * * *`) lub pusty ciąg `""` dla zadań manualnych. |
| **`tasks[].enabled`** | bool | Tak | `true` | Czy zadanie jest aktywne w harmonogramie. |
| **`tasks[].restore_enabled`**| bool | Tak | `false` | Zabezpieczenie przed przypadkowym przywróceniem danych (musi być `true`, aby odblokować przycisk *Restore*). |
| **`tasks[].exclude`** | array | Tak | `[]` | Lista masek plików wykluczonych z kopii (np. `["*.tmp", "~*", "Thumbs.db"]`). |
| **`tasks[].custom_flags`** | array | Tak | `[]` | Dodatkowe flagi wiersza poleceń dla `rsync` lub `rclone` (np. `["--fast-list", "--bwlimit=10M"]`). |
| **`tasks[].retention_days`** | int | Tak | `0` | Liczba dni przechowywania usuniętych plików w folderze kosza (`-trash/YYYY-MM-DD/`). Wartość `0` wyłącza kosz. |
| **`tasks[].next_task_id`** | int/null | Nie | `null` | ID kolejnego zadania uruchamianego automatycznie po pomyślnym zakończeniu tego zadania (pipeline). |
| **`tasks[].status`** | string/null | Nie | `null` | Ostatni status wykonania: `"OK"`, `"BŁĄD"`, `"Zatrzymane"`, `"RUNNING"`. |
| **`tasks[].last_run`** | string/null | Nie | `null` | Data i godzina ostatniego uruchomienia w formacie ISO. |
| **`tasks[].discord_webhook`**| string/null | Nie | `null` | URL webhooka Discord do wysyłania powiadomień. |
| **`tasks[].ntfy_url`** | string/null | Nie | `null` | URL ntfy.sh (np. `https://ntfy.sh/moje-alerty`). |
| **`tasks[].email_enabled`** | bool | Tak | `false` | Czy wysyłać powiadomienia na skrzynkę e-mail przez serwer SMTP zdefiniowany w `.env`. |
| **`tasks[].email_recipients`**| string/null| Nie | `null` | Adres(y) e-mail odbiorców rozdzielone przecinkami (np. `admin@domena.pl`). |
| **`tasks[].email_level`** | string | Tak | `"tylko_bledy"` | Kiedy wysyłać e-mail: `"wszystkie"` (sukces i błąd) lub `"tylko_bledy"`. |
| **`users[].username`** | string | Tak | - | Nazwa zarejestrowanego użytkownika. |
| **`users[].password`** | string | Tak | - | Skrót hasła w formacie Argon2id (`$argon2id$...`) lub bcrypt (`$2b$...`). |

---

### 3. Plik `rclone.conf`

Dla zadań typu `cloud` należy dostarczyć konfigurację zdalnych magazynów w `backend/config/rclone.conf`. 
Najwygodniej wygenerować go poleceniem:
```bash
rclone config
```
a następnie skopiować utworzony plik `~/.config/rclone/rclone.conf` do `backend/config/rclone.conf`.

---

### 4. Plik `env.example` (Frontend)

W `frontend/env.example` zdefiniowane jest opcjonalne `VITE_API_URL`. W przypadku wystawienia aplikacji za reverse proxy (np. Traefik, Nginx Proxy Manager, Cloudflare Tunnel) z własną domeną, wskaż tam docelowy adres URL backendu.

---

## 🏁 Uruchomienie Systemu

W katalogu głównym projektu uruchom:

```bash
# Budowa i uruchomienie kontenerów w tle
sudo docker compose up -d --build
```

Sprawdzenie statusu kontenerów:
```bash
sudo docker compose ps
```

Podgląd logów w czasie rzeczywistym:
```bash
sudo docker compose logs -f
```

Zatrzymanie systemu:
```bash
sudo docker compose down
```

---

## 🖥️ Korzystanie z Aplikacji

1. Otwórz w przeglądarce adres: `http://<ADRES_IP_NAS>:5173` (lub port `80` w środowisku produkcyjnym).
2. Zaloguj się domyślnym kontem administratora zdefiniowanym w pliku `.env`.
3. Na pulpicie zobaczysz kafelki zdefiniowanych zadań:
   - **Start (Play):** Dodaje natychmiastowe wykonanie zadania do kolejki.
   - **Stop (Kwadrat):** Wymusza natychmiastowe przerwanie trwającego procesu.
   - **Edycja:** Pozwala dostosować parametry zadania, powiadomienia i harmonogram.
   - **Logi:** Otwiera konsolę z podglądem logów rsync/rclone na żywo.
   - **Restore:** Odwraca kierunek synchronizacji i przywraca dane z kopii (wymaga włączenia opcji *Restore*).

---

## 🎛️ Wizualny Kreator Cron i Harmonogramowanie

Aplikacja posiada zintegrowany **Wizualny Kreator Cron (`CronBuilder`)**:

1. **Codziennie:** Wybór konkretnej godziny i minuty (np. `03:00` w nocy) oraz szybkie przyciski popularnych godzin nocnych (`01:00`, `02:00`, `03:00`, `04:00`).
2. **Co godzinę:** Uruchamianie w wybranej minucie każdej godziny (np. o pełnej godzinie `0 * * * *`).
3. **Co określony czas (Interval):** Wybór co ile godzin ma startować backup (co 2, 3, 4, 6, 8 lub 12 godzin).
4. **W wybrane dni tygodnia:** Łatwy wybór dni roboczych (Poniedziałek – Piątek) lub weekendów z określeniem godziny startu.
5. **Tylko ręcznie (Bez harmonogramu):** Zadanie otrzymuje pusty harmonogram (`""`). Jest w pełni aktywne i gotowe do startu, ale scheduler nie rejestruje dla niego wyzwalacza czasowego. Uruchamiasz je wyłącznie kliknięciem przycisku *Start* w panelu.
6. **Własny zapis (Zaawansowany):** Tradycyjne 5-polowe pole Cron dla zaawansowanych użytkowników.

---

## 📊 Podgląd Postępu i Transferu w Czasie Rzeczywistym

Gdy zadanie zostaje uruchomione (status `RUNNING`):
- Silnik `rsync` uruchamiany jest z flagą `--info=progress2`.
- Silnik `rclone` raportuje stan z flagami `--stats=1s --stats-one-line`.
- Backend streamuje wyjście procesu, a frontend co 1.5 sekundy odpytuje endpoint `GET /api/tasks/progress`.
- Na karcie aktywnego zadania wyświetla się:
  - **Pasek postępu** ze statusem procentowym (0–100%),
  - **Chwilowa prędkość transferu** (np. `28.4 MiB/s`),
  - **Licznik przesłanych plików** (np. `142 / 520 plików`),
  - **Szacowany czas do zakończenia (ETA)**.
- Po zakończeniu transferu odpytywanie natychmiast ustaje, nie obciążając procesora ani sieci NAS-a.

---

## 🔄 Tryby kopiowania (`mode`)

- **`mirror`:** Pełne lustro katalogu źródłowego. Jeśli plik został usunięty ze źródła, zostanie również usunięty z celu (lub przeniesiony do folderu `-trash/`, jeśli włączona jest retencja).
- **`copy`:** Bezpieczne kopiowanie przyrostowe. Nowe i zmodyfikowane pliki trafiają do celu, ale pliki usunięte ze źródła pozostają w miejscu docelowym nienaruszone.
- **`move`:** Przenoszenie danych. Po pomyślnym skopiowaniu pliki źródłowe są usuwane.

---

## 🔗 Łańcuchowanie zadań (`next_task_id`)

Za pomocą pola `next_task_id` można tworzyć wieloetapowe potoki:
1. **Krok 1 (Lokalny szybki mirror):** Dokumenty z NAS kopiowane na drugi dysk lokalny.
2. **Krok 2 (Chmura):** Po pomyślnym zakończeniu Kroku 1 automatycznie startuje kopia z dysku lokalnego do Google Drive / OneDrive.
3. **Krok 3 (Archiwum):** Po sukcesie Kroku 2 następuje archiwizacja zdjęć do chmury (lub zakończenie łańcucha, gdy `next_task_id: null`).

Wszystkie kroki przechodzą przez tę samą jednowątkową kolejkę, co eliminuje ryzyko przeciążenia dysków.

---

## 🗑️ Retencja i kosz

Gdy w zadaniu ustawiono `retention_days > 0` oraz tryb `mirror`:
- Pliki kasowane podczas synchronizacji trafiają do podfolderu `<destination>-trash/YYYY-MM-DD/`.
- Codziennie o **00:15** demon `trash_cleaner` automatycznie skanuje foldery kosza i usuwa wersje starsze niż wskazana liczba dni.
- Pliki logów zadań starsze niż 365 dni są również automatycznie czyszczone.

---

## 🔔 Powiadomienia

Aplikacja obsługuje 3 niezależne kanały powiadomień per zadanie:

1. **Discord Webhook (`discord_webhook`):** Wysyła sformatowaną wiadomość ze statusem wykonania, nazwą zadania i godziną.
2. **ntfy.sh Push (`ntfy_url`):** Wysyła natychmiastowe powiadomienie push na urządzenia mobilne z aplikacją ntfy.
3. **E-mail SMTP (`email_enabled`, `email_recipients`, `email_level`):**
   - Wymaga skonfigurowania sekcji `SMTP_*` w pliku `.env`.
   - Pozwala wybrać poziom raportowania: wysyłanie przy każdym zadaniu (`wszystkie`) lub wyłącznie w przypadku wystąpienia błędu (`tylko_bledy`).

---

## 📡 Referencja API

Wszystkie endpointy zarządzania zadaniami wymagają nagłówka `Authorization: Bearer <TOKEN_JWT>` lub `X-API-Key: <KLUCZ_Z_ENV>`.

| Metoda | Endpoint | Opis |
| :--- | :--- | :--- |
| `GET` | `/api/tasks` | Pobiera pełną konfigurację zadań, ustawień i użytkowników. |
| `POST` | `/api/tasks` | Tworzy nowe zadanie kopii zapasowej. |
| `PUT` | `/api/tasks/{task_id}` | Aktualizuje parametry istniejącego zadania. |
| `DELETE`| `/api/tasks/{task_id}` | Usuwa zadanie i wyrejestrowuje je ze schedulera. |
| `POST` | `/api/tasks/{task_id}/run` | Dodaje zadanie do kolejki natychmiastowego wykonania. |
| `POST` | `/api/tasks/{task_id}/stop`| Wymusza zatrzymanie aktywnego procesu transferu (`SIGTERM` -> `SIGKILL`). |
| `POST` | `/api/tasks/{task_id}/restore`| Uruchamia procedurę przywracania danych (wymaga `restore_enabled: true`). |
| `GET` | `/api/tasks/{task_id}/logs`| Pobiera ostatnie 200 linii najświeższego pliku logu danego zadania. |
| `GET` | `/api/tasks/progress` | Zwraca bieżący postęp (procent, prędkość, pliki, ETA) dla aktywnych zadań. |
| `GET` | `/api/browse?path=` | Bezpieczna przeglądarka podkatalogów wewnątrz `/storage`. |
| `POST` | `/api/auth/login` | Logowanie do panelu — zwraca token JWT. |
| `POST` | `/api/auth/register` | Rejestracja nowego użytkownika (aktywna tylko gdy `DISABLE_REGISTRATION=false`). |

---

## 🔐 Bezpieczeństwo

- **Uwierzytelnianie:** Haszowanie haseł algorytmem **Argon2id** oraz **bcrypt**.
- **Ochrona przed Path Traversal:** Endpoint przeglądarki katalogów `/api/browse` rygorystycznie sprawdza kanoniczne ścieżki za pomocą `os.path.realpath`, uniemożliwiając wyjście poza katalog `/storage`.
- **Niezależne konto awaryjne:** Administrator zdefiniowany w `.env` działa zawsze, nawet w przypadku wyczyszczenia pliku bazy użytkowników.
- **Blokada rejestracji:** Domyślnie włączona flaga `DISABLE_REGISTRATION=true` zabezpiecza instalację przed nieautoryzowanym tworzeniem kont.

---

## 📦 Instrukcja Migracji w Inne Miejsce

Przeniesienie systemu na nowy serwer sprowadza się do skopiowania katalogu i uruchomienia Dockera:

1. **Kopiowanie plików:** Skopiuj katalog aplikacji na nowy serwer (np. za pomocą `rsync`, `scp` lub archiwum ZIP).
2. **Konfiguracja:** Przenieś plik `.env` oraz `backend/config/config.json`.
3. **Wolumeny:** W `docker-compose.yml` dostosuj ścieżki po lewej stronie dwukropka w sekcji `volumes` do punktów montowania dysków na nowym serwerze.
4. **Start:** Uruchom kontenery poleceniem `sudo docker compose up -d --build`.

---

## 🛠️ Rozwiązywanie problemów

| Objaw | Prawdopodobna przyczyna | Rozwiązanie |
| :--- | :--- | :--- |
| **Błąd 403 / wylogowanie w aplikacji** | Rozbieżność kluczy API lub wygasły token JWT | Sprawdź czy zmienna `API_KEY` w `.env` jest poprawna, wyczyść ciasteczka przeglądarki i zaloguj się ponownie. |
| **Zadanie ma status RUNNING po restarcie serwera** | Kontener został zrestartowany w trakcie pracy zadania | Backend automatycznie oznacza przerwane zadania jako błąd przy starcie. Wystarczy uruchomić zadanie ponownie. |
| **Zadanie chmurowe zwraca błąd** | Brak autoryzacji w `rclone.conf` | Sprawdź plik `backend/config/rclone.conf` i upewnij się, że tokeny dostępowe do chmury są ważne. |
| **Przycisk Restore jest nieaktywny** | Zabezpieczenie zadania | Wejdź w edycję zadania i zaznacz opcję *Zezwól na operacje Restore*. |
| **Pasek postępu nie pokazuje prędkości** | Początkowa faza indeksowania plików | Przy bardzo dużej liczbie drobnych plików rsync/rclone najpierw buduje listę plików przed rozpoczęciem właściwego transferu. |

---

## ⚠️ Znane ograniczenia

- Konfiguracja w formacie flat-file (`config.json`) jest dedykowana dla pojedynczej instancji aplikacji — nie należy uruchamiać wielu kontenerów backendu współdzielących ten sam plik bez zewnętrznego mechanizmu blokowania.
- CORS jest domyślnie otwarty dla sieci lokalnej (`allow_origins=["*"]`). Przy wystawianiu panelu do publicznego internetu zalecane jest stosowanie Reverse Proxy (Nginx, Traefik, Caddy) z szyfrowaniem HTTPS.

---

## 📄 Licencja

Projekt udostępniony na licencji [MIT](LICENSE).
