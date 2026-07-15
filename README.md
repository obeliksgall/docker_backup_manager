# Docker Backup Manager

Nowoczesny, bezpieczny i w pełni kontenerowy system do zarządzania kopiami zapasowymi (lokalnymi oraz chmurowymi), dedykowany dla serwerów NAS oraz środowisk Linux. Aplikacja oferuje pełny podgląd logów w czasie rzeczywistym, kolejkowanie zadań zabezpieczające wydajność dyskową (I/O), łańcuchowanie zadań, powiadomienia (Discord/ntfy) oraz rozproszoną autoryzację użytkowników — bez potrzeby uruchamiania ciężkiej bazy danych SQL.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Spis treści

1. [Architektura i główne funkcje](#-architektura-i-główne-funkcje)
2. [Struktura projektu](#️-struktura-projektu)
3. [Wymagania wstępne](#-wymagania-wstępne)
4. [Konfiguracja środowiska](#️-wymagania-i-konfiguracja-środowiska)
5. [Uruchomienie systemu](#-uruchomienie-systemu)
6. [Korzystanie z aplikacji](#-korzystanie-z-aplikacji)
7. [Tryby kopiowania (`mode`)](#-tryby-kopiowania-mode)
8. [Łańcuchowanie zadań](#-łańcuchowanie-zadań-next_task_id)
9. [Retencja i kosz](#️-retencja-i-kosz)
10. [Powiadomienia](#-powiadomienia)
11. [Referencja API](#-referencja-api)
12. [Bezpieczeństwo](#-bezpieczeństwo)
13. [Instrukcja migracji w inne miejsce](#-instrukcja-migracji-w-inne-miejsce)
14. [Rozwiązywanie problemów](#-rozwiązywanie-problemów)
15. [Znane ograniczenia](#️-znane-ograniczenia)
16. [Licencja](#-licencja)

---

## 🚀 Architektura i Główne Funkcje

- **Backend (FastAPI, `backend/main.py`):** Zarządza zadaniami, komunikacją z silnikami kopiowania (`rsync` dla kopii lokalnych, `rclone` dla kopii chmurowych), kolejkowaniem zadań (APScheduler z `ThreadPoolExecutor(max_workers=1)`, co serializuje operacje I/O i chroni dyski NAS przed przeciążeniem) oraz bezpieczeństwem (JWT + bcrypt + statyczny klucz API).
- **Frontend (React + TypeScript + Tailwind CSS + Vite):** Elegancki dashboard z ciemnym motywem, dynamicznym drzewem katalogów NAS (przeglądarka folderów), konsolą logów na żywo, przełącznikiem języka PL/EN oraz stanowym zabezpieczeniem sesji (JWT w `localStorage`).
- **Baza danych flat-file:** Cała konfiguracja zadań oraz użytkowników zapisywana jest atomowo w jednym pliku `backend/config/config.json` (zwalidowanym schematem `config.schema.json`), co eliminuje potrzebę utrzymywania ciężkich baz SQL i ułatwia przenoszenie systemu.
- **Łańcuchowanie zadań:** każde zadanie może wskazywać `next_task_id` — po sukcesie automatycznie uruchamiane jest kolejne zadanie w kolejce (np. lokalny mirror → synchronizacja do chmury).
- **Powiadomienia:** integracja z Discord (webhook) oraz ntfy.sh, konfigurowana per zadanie.
- **Retencja wersji ("kosz"):** przy trybie `mirror` usuwane pliki trafiają do datowanego folderu `-trash/YYYY-MM-DD/`, a najstarsze wersje są automatycznie czyszczone zgodnie z `retention_days` (cron nocny o 00:15).
- **Restore z zabezpieczeniem:** przywracanie danych jest domyślnie zablokowane per zadanie (`restore_enabled`) — trzeba je świadomie włączyć w edycji zadania.
- **Dwujęzyczny interfejs:** pełne tłumaczenia PL/EN (i18next) z przełącznikiem w nagłówku.

---

## 🏗️ Struktura Projektu

```text
.
├── docker-compose.yml
├── .env                        # tworzony ręcznie na podstawie env.example
├── LICENSE
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt        # pyjwt, bcrypt (fastapi/uvicorn/apscheduler instalowane w Dockerfile/compose)
│   ├── main.py                 # aktywny punkt wejścia API (logi/komunikaty PL)
│   ├── main_EN.py              # ta sama logika, komunikaty/komentarze EN (utrzymywać w synchronizacji)
│   ├── config/
│   │   ├── config.json         # flat-file "baza danych" zadań i użytkowników
│   │   ├── config.schema.json  # schemat walidacji JSON dla config.json
│   │   └── rclone.conf         # konfiguracja zdalnych magazynów rclone (remotes)
│   └── logs/                   # tworzone w runtime: app.log + logi per zadanie
│       └── tasks/<slug-zadania>/<timestamp>.log
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── env.example
    └── src/
        ├── main.tsx             # punkt wejścia React
        ├── App.tsx              # główny widok dashboardu, cały stan aplikacji
        ├── Login.tsx             # ekran logowania (bramka przed dashboardem)
        ├── TaskModal.tsx         # formularz tworzenia/edycji/klonowania zadania
        ├── LogModal.tsx          # podgląd ostatnich 200 linii logu zadania
        ├── FolderBrowserModal.tsx # przeglądarka katalogów /storage (dla source/destination)
        ├── i18n.ts               # konfiguracja i18next + słowniki PL/EN
        ├── App.css / index.css
        └── FolderBrowserModal.tsx
```

Katalogi `./data` (storage backupów) oraz `./backend/logs` są tworzone automatycznie przy pierwszym uruchomieniu i montowane jako wolumeny Dockera — nie trzeba ich zakładać ręcznie.

---

## ✅ Wymagania Wstępne

- Docker Engine oraz wtyczka Docker Compose (v2, polecenie `docker compose`).
- Dostęp `sudo`/root na maszynie hosta (montowanie wolumenów, porty < 1024 nie są wymagane, ale operacje na dyskach NAS zwykle tego wymagają).
- Skonfigurowane zdalne magazyny w `rclone.conf`, jeśli planowane są zadania typu `cloud` (patrz [rclone config](https://rclone.org/docs/)).
- Otwarte porty `8000` (API) i `5173` (frontend) w sieci lokalnej/firewallu.

---

## ⚙️ Wymagania i Konfiguracja Środowiska

### 1. Plik `.env`

Utwórz plik `.env` w katalogu głównym projektu (na podstawie `env.example`). Zmienne te sterują zachowaniem kontenerów i są automatycznie wstrzykiwane przez demona Docker do kodu źródłowego.

```env
# Domyślne poświadczenia administratora (używane, gdy baza użytkowników w pliku JSON jest pusta)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=TwojeSuperTajneHasloStartowe123!

# Bezpieczeństwo sesji i tokenów JWT
JWT_SECRET=wpisz_tutaj_bardzo_dlugi_losowy_ciag_znakow_alfanumerycznych

# Blokada rejestracji (true = brak możliwości tworzenia kont z poziomu aplikacji)
DISABLE_REGISTRATION=true

# Klucze API (Kompatybilność komunikacji frontend <-> backend, wartości MUSZĄ być identyczne)
API_KEY=TwojKluczAPIZabezpieczajacyKomunikacje
VITE_API_KEY=TwojKluczAPIZabezpieczajacyKomunikacje
```

> ⚠️ `ADMIN_PASSWORD`, `JWT_SECRET` oraz `API_KEY` powinny być długimi, losowymi ciągami znaków — nigdy nie zostawiaj wartości przykładowych w środowisku produkcyjnym.

### 2. Plik `config.json` (baza danych flat-file)

Przed pierwszym uruchomieniem zainicjalizuj strukturę bazy danych w `backend/config/config.json`. Jeśli przeprowadzasz czystą instalację, plik musi zawierać poprawny obiekt JSON:

```json
{
  "settings": {
    "rclone_flags": ["--buffer-size=16M", "--transfers=2"]
  },
  "tasks": [],
  "users": []
}
```

- `settings.rclone_flags` — domyślne flagi dołączane do każdego polecenia `rclone`, jeśli dane zadanie nie ma zdefiniowanych własnych `custom_flags`.
- Struktura pliku jest opisana i walidowana przez `backend/config/config.schema.json`.
- *Uwaga: Po zarejestrowaniu użytkownika przez aplikację (gdy `DISABLE_REGISTRATION=false`), jego hasło zostanie automatycznie zapisane w tablicy `users` w formie bezpiecznego hasza bcrypt. Plik ten rośnie wraz z dodawaniem nowych zadań.*

### 3. Plik `rclone.conf`

Jeśli planujesz zadania typu `cloud`, skonfiguruj zdalne magazyny (Google Drive, OneDrive, S3, itd.) w `backend/config/rclone.conf` — najwygodniej lokalnie poleceniem `rclone config`, a następnie skopiuj wygenerowany plik na serwer.

### 4. Plik `env.example` (frontend)

`frontend/env.example` pokazuje wymaganą zmienną `VITE_API_KEY` — musi mieć tę samą wartość co `API_KEY` w głównym `.env`, inaczej frontend nie przejdzie autoryzacji API (błąd 403).

---

## 🏁 Uruchomienie Systemu

W folderze głównym projektu wykonaj w terminalu następujące polecenia, aby skompilować i uruchomić aplikację:

```bash
# 1. Zbudowanie obrazów i uruchomienie kontenerów w tle na czysto
sudo docker compose up -d --build

# 2. Weryfikacja statusu działania procesów
sudo docker compose ps

# 3. Podgląd logów w czasie rzeczywistym w razie problemów startowych
sudo docker compose logs -f backup-backend
sudo docker compose logs -f backup-frontend

# 4. Zatrzymanie systemu
sudo docker compose down
```

Aplikacja frontendowa będzie dostępna w przeglądarce pod adresem IP serwera NAS na porcie `5173` (`http://IP_NAS:5173`), a API backendu pod portem `8000` (`http://IP_NAS:8000`).

Oba kontenery montują swoje katalogi źródłowe jako wolumeny i uruchamiają się w trybie „hot-reload” (`uvicorn --reload` / `vite dev`) — zmiany w `backend/main.py` lub plikach w `frontend/src/` są widoczne od razu, bez potrzeby przebudowy obrazu.

---

## 🖥️ Korzystanie z Aplikacji

1. **Logowanie** — przy pierwszym uruchomieniu zaloguj się danymi z `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`). Token JWT oraz nazwa użytkownika są zapisywane w `localStorage` przeglądarki.
2. **Dashboard** — każde zadanie backupu wyświetlane jest jako karta z informacją o typie (lokalny/chmurowy), trybie, harmonogramie cron oraz statusie ostatniego uruchomienia (`Sukces`, `Błąd`, `W trakcie...`, `Zatrzymane`, `Nieuruchamiane`).
3. **Tworzenie/edycja zadania** — przycisk „Nowe zadanie” otwiera formularz (`TaskModal`), w którym określasz: typ (lokalny/chmurowy), nazwę, ścieżkę źródłową i docelową (z przeglądarką katalogów `/storage`), tryb kopiowania, harmonogram cron, liczbę dni retencji, wykluczenia plików, dodatkowe flagi `rclone` (tylko dla zadań chmurowych), zadanie następne w łańcuchu, webhooki powiadomień oraz przełączniki „aktywne w harmonogramie” i „zezwól na restore”.
4. **Klonowanie zadania** — ikona kopiowania na karcie zadania otwiera formularz wypełniony danymi istniejącego zadania (bez ID), co ułatwia tworzenie podobnych zadań.
5. **Uruchomienie ręczne** — przycisk „Uruchom” dodaje zadanie do jednowątkowej kolejki wykonawczej (nie przerywa to harmonogramu cron).
6. **Zatrzymanie zadania** — przycisk „Stop” widoczny tylko podczas wykonywania zadania; wysyła `SIGTERM`, a po 5 sekundach `SIGKILL`, jeśli proces się nie zakończy.
7. **Podgląd logów** — ikona pliku otwiera ostatnie 200 linii najnowszego logu danego zadania (`LogModal`).
8. **Restore** — dostępny tylko, jeśli zadanie ma włączoną opcję „Zezwól na operacje Restore”; wymaga dodatkowego potwierdzenia w interfejsie, ponieważ nadpisuje dane źródłowe.
9. **Zmiana języka** — przełącznik PL/EN w prawym górnym rogu nagłówka, zapamiętywany w `localStorage`.

---

## 🔄 Tryby kopiowania (`mode`)

| Tryb | Lokalnie (`rsync`) | Chmurowo (`rclone`) | Opis |
|---|---|---|---|
| `mirror` | `rsync --delete [--backup --backup-dir=...]` | `rclone sync [--backup-dir=...]` | Cel staje się dokładnym odbiciem źródła — pliki usunięte w źródle są usuwane (lub przenoszone do kosza, jeśli `retention_days > 0`) w celu. |
| `copy` | `rsync -rtv` | `rclone copy` | Dopisuje/aktualizuje pliki w celu, nigdy nic nie usuwa. |
| `move` | `rsync --remove-source-files` | `rclone move` | Przenosi pliki ze źródła do celu, usuwając je ze źródła po udanym transferze. |

Wykluczenia (`exclude`) są stosowane jako `--exclude=<wzorzec>` (rsync) lub `--exclude <wzorzec>` (rclone) dla każdego zdefiniowanego wzorca.

---

## 🔗 Łańcuchowanie zadań (`next_task_id`)

Zadanie może wskazywać ID kolejnego zadania do uruchomienia po swoim sukcesie (`next_task_id`). Pozwala to budować wieloetapowe pipeline'y, np.:

1. **Zadanie #1** — kopia lokalna dokumentów (`local`, `mirror`) → po sukcesie wywołuje...
2. **Zadanie #2** — synchronizacja tej kopii do chmury (`cloud`, `copy`) → po sukcesie wywołuje...
3. **Zadanie #3** — kopia zdjęć do innej chmury (koniec łańcucha, `next_task_id: null`).

Uruchomienie łańcuchowe trafia do tej samej jednowątkowej kolejki co zadania ręczne i cron, więc nie koliduje z innymi operacjami dyskowymi. Jeśli wskazane `next_task_id` nie istnieje w `config.json`, zapisywane jest odpowiednie ostrzeżenie w logu aplikacji.

---

## 🗑️ Retencja i kosz

Gdy `retention_days > 0` i tryb to `mirror`, usuwane podczas synchronizacji pliki trafiają do folderu `<destination>-trash/YYYY-MM-DD/` zamiast być kasowane od razu. Codziennie o **00:15** uruchamiane jest zadanie `trash_cleaner`, które:

- usuwa najstarsze datowane podfoldery kosza ponad limit `retention_days` (dla każdego aktywnego zadania z ustawioną retencją),
- usuwa pliki logów starsze niż 365 dni z `backend/logs/tasks/`.

---

## 🔔 Powiadomienia

Każde zadanie może mieć niezależnie skonfigurowane:

- **Discord webhook** (`discord_webhook`) — wiadomość tekstowa ze statusem (✅/❌) wysyłana po zakończeniu zadania.
- **ntfy.sh** (`ntfy_url`) — powiadomienie push z tytułem `Backup: <nazwa zadania>`.

Powiadomienia są wysyłane dla statusów: sukces, błąd oraz ręczne zatrzymanie zadania („Zatrzymane na żądanie 🛑”). Puste pola lub wartości placeholder (`string`, `null`, `None`) są ignorowane.

---

## 📡 Referencja API

Wszystkie endpointy pod `/api/tasks*` oraz `/api/browse` wymagają nagłówka `X-API-Key` zgodnego z `API_KEY` z `.env`. Endpointy logowania/rejestracji nie wymagają klucza API.

| Metoda | Endpoint | Opis |
|---|---|---|
| `GET` | `/api/tasks` | Zwraca pełną konfigurację (`tasks`, `users`, `settings`). |
| `POST` | `/api/tasks` | Tworzy nowe zadanie (waliduje istnienie ścieżki źródłowej dla `local`). |
| `PUT` | `/api/tasks/{task_id}` | Aktualizuje istniejące zadanie. |
| `DELETE` | `/api/tasks/{task_id}` | Usuwa zadanie i wypisuje je z harmonogramu. |
| `POST` | `/api/tasks/{task_id}/run` | Dodaje ręczne uruchomienie zadania do kolejki. |
| `POST` | `/api/tasks/{task_id}/stop` | Wymusza zatrzymanie aktywnego procesu (`SIGTERM` → `SIGKILL`). |
| `POST` | `/api/tasks/{task_id}/restore` | Uruchamia przywracanie danych (wymaga `restore_enabled: true`). |
| `GET` | `/api/tasks/{task_id}/logs` | Zwraca ostatnie 200 linii najnowszego logu zadania. |
| `GET` | `/api/browse?path=` | Przegląda podkatalogi wewnątrz `/storage` (dla przeglądarki folderów w UI). |
| `POST` | `/api/auth/login` | Logowanie — zwraca token JWT (admin z `.env` lub zarejestrowany użytkownik). |
| `POST` | `/api/auth/register` | Rejestracja nowego użytkownika (zablokowana, gdy `DISABLE_REGISTRATION=true`). |

---

## 🔐 Bezpieczeństwo

- **Dwuwarstwowa autoryzacja:** statyczny klucz `X-API-Key` (współdzielony sekret frontend↔backend) chroni wszystkie endpointy operacyjne, a JWT (`JWT_SECRET`) obsługuje sesje poszczególnych użytkowników.
- **Hasła użytkowników** są haszowane algorytmem bcrypt przed zapisem do `config.json` — nigdy nie są przechowywane jawnie.
- **Konto administratora** z `.env` działa zawsze, niezależnie od zawartości `users` w `config.json` — przydatne do odzyskania dostępu po zapomnieniu haseł (patrz sekcja migracji).
- **Rejestracja** można całkowicie zablokować ustawiając `DISABLE_REGISTRATION=true` (zalecane w środowisku produkcyjnym z jednym administratorem).
- **Ochrona ścieżek:** endpoint `/api/browse` ogranicza nawigację wyłącznie do katalogu `/storage`, uniemożliwiając przechodzenie poza wyznaczony obszar (np. `../../etc`).
- Zmień domyślne wartości `API_KEY`, `JWT_SECRET` oraz `ADMIN_PASSWORD` przed wystawieniem aplikacji poza sieć lokalną — CORS jest skonfigurowany z `allow_origins=["*"]`, co zakłada zaufaną sieć lokalną, a nie ekspozycję do internetu bez dodatkowej warstwy (np. reverse proxy z HTTPS i autoryzacją).

---

## 📦 Instrukcja Migracji w Inne Miejsce

Dzięki pełnej konteneryzacji przeniesienie systemu na inny serwer NAS lub VPS sprowadza się do 4 kroków:

1. **Kopiowanie plików:** Spakuj i przenieś katalog projektu na nową maszynę (np. za pomocą `scp`, `sftp` lub zewnętrznego nośnika).
2. **Zachowanie lub reset danych:**
   - Jeśli chcesz przenieść **wszystkie zadania i konta**, przenieś nienaruszony plik `config.json`.
   - Jeśli przenosisz zadania, ale chcesz **zresetować zapomniane hasła**, otwórz plik `config.json` na nowej maszynie i wyczyść tablicę użytkowników do postaci `"users": []`. System pozwoli wtedy na ponowne zalogowanie się danymi startowymi z pliku `.env`.
3. **Dostosowanie ścieżek:** Otwórz `docker-compose.yml` na nowym serwerze i zaktualizuj sekcję `volumes` (mapowanie folderów źródłowych `/storage` oraz docelowych), dostosowując je do punktów montowania dysków na nowej maszynie.
4. **Rozruch:** Wykonaj `sudo docker compose down && sudo docker compose up -d --build`. System od razu zainstaluje wymagane pakiety kryptograficzne w kontenerze i podniesie panel zabezpieczony hasłem.

---

## 🛠️ Rozwiązywanie problemów

| Objaw | Prawdopodobna przyczyna | Rozwiązanie |
|---|---|---|
| Frontend zwraca błąd 403 / wylogowuje po chwili | `VITE_API_KEY` ≠ `API_KEY` w `.env` | Ustaw identyczną wartość dla obu zmiennych i przebuduj kontenery. |
| Zadanie utyka na statusie „RUNNING” po restarcie kontenera | Kontener został zabity w trakcie działania procesu | Backend automatycznie resetuje takie zadania na status „Błąd” przy starcie — uruchom zadanie ponownie ręcznie. |
| Zadanie chmurowe kończy się błędem | Brak lub błędna konfiguracja zdalnego magazynu | Sprawdź `backend/config/rclone.conf` oraz uruchom `rclone lsd <remote>:` wewnątrz kontenera backendu w celu weryfikacji. |
| Przycisk „Restore” jest zablokowany | Zadanie nie ma włączonej opcji `restore_enabled` | Włącz „Zezwól na operacje Restore” w edycji zadania. |
| Powiadomienia Discord/ntfy nie przychodzą | Puste pole lub nieprawidłowy URL webhooka | Zweryfikuj URL w edycji zadania; błędy są zapisywane w `backend/logs/app.log`. |
| Brak dostępu do katalogu w przeglądarce folderów | Ścieżka znajduje się poza zamontowanym `/storage` | Zamapuj dodatkowy wolumen w `docker-compose.yml` pod `/storage/...`. |

Diagnostykę zawsze zaczynaj od `sudo docker compose logs -f backup-backend` oraz podglądu `backend/logs/app.log` i logów konkretnego zadania w `backend/logs/tasks/<slug>/`.

---

## ⚠️ Znane ograniczenia

- Brak automatycznych testów jednostkowych/integracyjnych oraz pipeline'u CI.
- Konfiguracja przechowywana jest w jednym pliku JSON bez blokad współbieżności na poziomie plikowym — nie zaleca się uruchamiania wielu instancji backendu na tym samym pliku `config.json`.
- `backend/main_EN.py` to zduplikowany plik z angielskimi komunikatami — nie jest aktywnie używany przez `docker-compose.yml`/`Dockerfile`, ale wymaga ręcznej synchronizacji przy zmianach logiki w `main.py`.
- CORS dopuszcza dowolne pochodzenie (`allow_origins=["*"]`) — aplikacja jest zaprojektowana do pracy w zaufanej sieci lokalnej, a nie bezpośredniej ekspozycji do internetu.

---

## 📄 Licencja

Projekt udostępniony na licencji [MIT](LICENSE).
