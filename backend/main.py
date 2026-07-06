import os
import json
import subprocess
import urllib.request

import bcrypt
import jwt

from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends
from pydantic import BaseModel
from typing import Optional, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
# IMPORT WYKONAWCY WĄTKÓW DLA KOLEJKOWANIA
from apscheduler.executors.pool import ThreadPoolExecutor

from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

app = FastAPI(title="Docker Backup Manager API")

# Pobieramy nowe zmienne z .env
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
DISABLE_REGISTRATION = os.getenv("DISABLE_REGISTRATION", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-me")

print(f"DEBUG AUTH -> USER: {ADMIN_USERNAME}, PASS: {ADMIN_PASSWORD}, REG_DISABLED: {DISABLE_REGISTRATION}")

class LoginSchema(BaseModel):
    username: str
    password: str

class RegisterSchema(BaseModel):
    username: str
    password: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # W sieci lokalnej pozwalamy na dostęp z dowolnego źródła (Twojego komputera/NAS-a)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_PATH = "/app/config/config.json"
RCLONE_CONFIG_PATH = "/app/config/rclone.conf"
BASE_STORAGE = "/storage"
LOGS_BASE_DIR = "/app/logs/tasks"
APP_LOG_PATH = "/app/logs/app.log"

# Pobieramy klucz ze zmiennej środowiskowej kontenera. Jeśli go nie ma, domyślnie ustawiamy bezpieczny fallback.
API_KEY_SECRET = os.getenv("API_KEY", "DomyślnyKluczBezpieczeństwa")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY_SECRET:
        raise HTTPException(
            status_code=403, 
            detail="Brak dostępu: Nieprawidłowy lub brakujący klucz API (X-API-Key)."
        )
    return api_key

# --- POPRAWKA: KONFIGURACJA KOLEJKOWANIA ZADAŃ NA NAS ---
# max_workers=1 oznacza wykonywanie zadań jedno po drugim. 
# Zmień na 3, jeśli chcesz pozwolić na maksymalnie 3 zadania jednocześnie.
executors = {
    'default': ThreadPoolExecutor(max_workers=1)
}
scheduler = BackgroundScheduler(executors=executors)

# --- SCHEMAT WALIDACJI DANYCH ---
class TaskSchema(BaseModel):
    name: str
    source: str
    destination: str
    type: str                  # "local" lub "cloud"
    mode: str                  # "mirror", "incremental", "move"
    schedule: str              # Zapis Cron, np. "0 3 * * *"
    enabled: bool = True       # Czy aktywne w harmonogramie
    restore_enabled: bool = False # Bezpiecznik dla Restore
    exclude: List[str] = []    # Ignorowane pliki/foldery
    retention_days: int = 0    # Liczba trzymanych wersji kosza (0 = brak)
    discord_webhook: Optional[str] = None
    ntfy_url: Optional[str] = None

# --- FUNKCJE POMOCNICZE ---
def log_to_app(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # POPRAWKA: Automatycznie twórz folder logs, jeśli nie istnieje
    os.makedirs(os.path.dirname(APP_LOG_PATH), exist_ok=True)
    
    with open(APP_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def send_notification(task_name: str, status: str, discord_url: str = None, ntfy_url: str = None):
    emoji = "✅" if status in ["OK", "SUKCES"] else "❌"
    msg = f"{emoji} Zadanie '{task_name}' zakończyło się statusem: {status}."
    
    if discord_url and discord_url not in ["string", "null", "None", ""]:
        try:
            payload = json.dumps({"content": msg}).encode("utf-8")
            req = urllib.request.Request(
                discord_url, 
                data=payload, 
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                }
            )
            with urllib.request.urlopen(req) as res: pass
        except Exception as e: log_to_app(f"Błąd powiadomienia Discord: {str(e)}")

    if ntfy_url and ntfy_url not in ["string", "null", "None", ""]:
        try:
            payload = msg.encode("utf-8")
            req = urllib.request.Request(
                ntfy_url, 
                data=payload, 
                headers={
                    "Title": f"Backup: {task_name}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                }
            )
            with urllib.request.urlopen(req) as res: pass
        except Exception as e: log_to_app(f"Błąd powiadomienia ntfy: {str(e)}")

def save_config(data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_all_tasks():
    if not os.path.exists(CONFIG_PATH):
        return {"tasks": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# --- AUTOMATYCZNE CZYSZCZENIE KOSZA (RETENCJA WERSJI) ---
def clean_old_trash_folders(task: dict):
    retention_limit = task.get("retention_days", 0)
    if retention_limit <= 0:
        return

    log_to_app(f"Uruchamiono czyszczenie kosza dla zadania '{task['name']}' (Limit wersji: {retention_limit}).")

    if task["type"] == "local":
        trash_base = task["destination"].rstrip("/") + "-trash"
        if not os.path.exists(trash_base):
            return
        try:
            subdirs = [os.path.join(trash_base, d) for d in os.listdir(trash_base)]
            subdirs = [d for d in subdirs if os.path.isdir(d)]
            subdirs.sort()
            while len(subdirs) > retention_limit:
                oldest_folder = subdirs.pop(0)
                subprocess.run(["rm", "-rf", oldest_folder])
                log_to_app(f"Retencja lokalna: Usunięto najstarszy folder kosza: {oldest_folder}")
        except Exception as e:
            log_to_app(f"Błąd czyszczenia kosza lokalnego: {str(e)}")

    elif task["type"] == "cloud":
        trash_base = task["destination"].rstrip("/") + "-trash"
        try:
            cmd_list = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "lsf", trash_base, "--dirs-only"]
            result = subprocess.run(cmd_list, capture_output=True, text=True)
            if result.returncode != 0:
                return
            subdirs = [d.strip("/") for d in result.stdout.splitlines() if d.strip()]
            subdirs.sort()
            while len(subdirs) > retention_limit:
                oldest_folder_name = subdirs.pop(0)
                full_remote_trash_path = f"{trash_base}/{oldest_folder_name}"
                subprocess.run(["rclone", f"--config={RCLONE_CONFIG_PATH}", "purge", full_remote_trash_path])
                log_to_app(f"Retencja chmury: Usunięto najstarszy folder kosza: {full_remote_trash_path}")
        except Exception as e:
            log_to_app(f"Błąd czyszczenia kosza w chmurze: {str(e)}")

def clean_all_trash_folders_cron():
    log_to_app("Harmonogram: Uruchomiono nocne czyszczenie kosza dla wszystkich zadań.")
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if task.get("enabled", True) and task.get("retention_days", 0) > 0:
            clean_old_trash_folders(task)

# --- SILNIK BACKUPU ---
def execute_backup_process(task: dict):
    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")
    
    log_to_app(f"Uruchamianie zadania ({task['type']} - {task.get('mode', 'mirror')}): {task['name']}.")
    cmd = []
    
    if task["type"] == "local":
        os.makedirs(task["destination"], exist_ok=True)
        source_path = task["source"].rstrip("/") + "/"
        cmd = ["rsync", "-rtv"]
        
        if task.get("mode", "mirror") == "mirror":
            cmd.append("--delete")
            if task.get("retention_days", 0) > 0:
                trash_dir = task["destination"].rstrip("/") + f"-trash/{today_str}/"
                os.makedirs(trash_dir, exist_ok=True)
                cmd.extend(["--backup", f"--backup-dir={trash_dir}"])
        elif task.get("mode") == "move":
            cmd.append("--remove-source-files")
            
        for ex in task.get("exclude", []):
            if ex: cmd.append(f"--exclude={ex}")
        cmd.extend([source_path, task["destination"]])

    elif task["type"] == "cloud":
        cmd = ["rclone", f"--config={RCLONE_CONFIG_PATH}"]
        if task.get("mode", "mirror") == "mirror":
            cmd.append("sync")
            if task.get("retention_days", 0) > 0:
                trash_dir = task["destination"].rstrip("/") + f"-trash/{today_str}"
                cmd.append(f"--backup-dir={trash_dir}")
        elif task.get("mode") == "move":
            cmd.append("move")
        else:
            cmd.append("copy")
            
        for ex in task.get("exclude", []):
            if ex: cmd.extend(["--exclude", ex])
        cmd.extend([task["source"], task["destination"], "-v"])
        
    else:
        return

    try:
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== START BACKUP ({task['type'].upper()}): {task['name']} ===\n")
            log_file.write(f"Komenda: {' '.join(cmd)}\n\n")
            process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True)
            
        final_status = "OK" if process.returncode == 0 else "Błąd"
        
        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task["id"]:
                t["status"] = final_status
                break
        save_config(config)
        
        log_to_app(f"Zadanie {task['name']} zakończone status: {final_status}.")
        send_notification(task["name"], final_status, discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
        
        if final_status == "OK":
            clean_old_trash_folders(task)
    except Exception as e:
        log_to_app(f"Krytyczny błąd {task['name']}: {str(e)}")

# --- SILNIK RESTORE ---
def execute_restore_process(task: dict):
    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_RESTORE")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")
    
    log_to_app(f"Uruchamianie PRZYWRACANIA dla zadania: {task['name']}.")
    
    if task["type"] == "local":
        os.makedirs(task["source"], exist_ok=True)
        dest_path = task["destination"].rstrip("/") + "/"
        cmd = ["rsync", "-rtv", dest_path, task["source"]]
    elif task["type"] == "cloud":
        cmd = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "copy", task["destination"], task["source"], "-v"]
    else:
        return

    try:
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== START RESTORE: {task['name']} ===\n\n")
            process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True)
        status = "SUKCES" if process.returncode == 0 else "BŁĄD"
        log_to_app(f"Przywracanie {task['name']} zakończone: {status}.")
        send_notification(f"RESTORE: {task['name']}", status, discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
    except Exception as e:
        log_to_app(f"Błąd przywracania {task['name']}: {str(e)}")

# --- OBSŁUGA HARMONOGRAMU ---
def add_task_to_scheduler(task: dict):
    if not task.get("enabled", True):
        if scheduler.get_job(str(task["id"])):
            scheduler.remove_job(str(task["id"]))
            log_to_app(f"Usunięto z harmonogramu (wyłączone): '{task['name']}'")
        return
    try:
        trigger = CronTrigger.from_crontab(task["schedule"])
        scheduler.add_job(
            execute_backup_process, trigger=trigger, args=[task],
            id=str(task["id"]), name=task["name"], replace_existing=True
        )
        log_to_app(f"Zarejestrowano w harmonogramie: '{task['name']}' ({task['schedule']})")
    except Exception as e:
        log_to_app(f"Błąd rejestracji harmonogramu dla '{task['name']}': {str(e)}")

def load_all_tasks_into_scheduler():
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if "mode" not in task: task["mode"] = "mirror"
        add_task_to_scheduler(task)
        
    scheduler.add_job(clean_all_trash_folders_cron, trigger=CronTrigger.from_crontab("15 0 * * *"), id="trash_cleaner", replace_existing=True)

@app.on_event("startup")
def startup_event():
    load_all_tasks_into_scheduler()
    scheduler.start()
    log_to_app("Harmonogram (Scheduler) i system retencji uruchomiony (Kolejkowanie aktywne).")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

# --- ENDPOINTY API ---
@app.get("/api/tasks", dependencies=[Depends(verify_api_key)])
def get_tasks():
    return get_all_tasks()

@app.post("/api/tasks", dependencies=[Depends(verify_api_key)])
def create_task(task: TaskSchema):
    config = get_all_tasks()
    existing_ids = [t["id"] for t in config.get("tasks", [])]
    new_id = max(existing_ids) + 1 if existing_ids else 1
    
    if not os.path.exists(task.source):
        raise HTTPException(status_code=400, detail=f"Brak katalogu: {task.source}")
        
    new_task = task.dict()
    new_task["id"] = new_id
    new_task["status"] = "New"
    
    config.setdefault("tasks", []).append(new_task)
    save_config(config)
    add_task_to_scheduler(new_task)
    log_to_app(f"Utworzono zadanie: {task.name}")
    return {"task": new_task}

@app.put("/api/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
def update_task(task_id: int, fields: TaskSchema):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    idx = next((i for i, t in enumerate(tasks) if t["id"] == task_id), None)
    
    if idx is None: raise HTTPException(status_code=404, detail="Brak zadania")
    if not os.path.exists(fields.source): raise HTTPException(status_code=400, detail="Brak źródła")
    
    updated_task = fields.dict()
    updated_task["id"] = task_id
    updated_task["status"] = tasks[idx].get("status", "New")
    
    tasks[idx] = updated_task
    save_config(config)
    add_task_to_scheduler(updated_task)
    log_to_app(f"Zaktualizowano zadanie ID {task_id}: {fields.name}")
    return {"task": updated_task}

@app.delete("/api/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
def delete_task(task_id: int):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    if not any(t["id"] == task_id for t in tasks): raise HTTPException(status_code=404, detail="Brak zadania")
    
    config["tasks"] = [t for t in tasks if t["id"] != task_id]
    save_config(config)
    if scheduler.get_job(str(task_id)): scheduler.remove_job(str(task_id))
    log_to_app(f"Usunięto zadanie ID {task_id}.")
    return {"message": "Zadanie usunięte"}

# --- POPRAWKA: RĘCZNE WYWOŁANIE TRAFIA DO KOLEJKI SCHEDULERA (ThreadPoolExecutor) ---
@app.post("/api/tasks/{task_id}/run", dependencies=[Depends(verify_api_key)])
def run_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Brak zadania")
    
    # Zamiast BackgroundTasks, wrzucamy bezpośrednio do kolejki wykonawczej z limitami wątków
    scheduler.add_job(
        execute_backup_process, 
        args=[task], 
        id=f"manual_{task_id}_{int(datetime.now().timestamp())}", 
        name=f"Manual Run: {task['name']}"
    )
    log_to_app(f"Ręczne wywołanie zadania ID {task_id} dodane do kolejki wątków.")
    return {"message": "Zadanie przekazane do kolejki wykonawczej (wykonywanie jedno po drugim)."}

# --- POPRAWKA: RĘCZNE WYWOŁANIE RESTORE TRAFIA DO TEJ SAMEJ KOLEJKI ---
@app.post("/api/tasks/{task_id}/restore", dependencies=[Depends(verify_api_key)])
def restore_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Brak zadania")
    if not task.get("restore_enabled", False):
        raise HTTPException(status_code=400, detail="Restore jest zablokowane w konfiguracji.")
        
    scheduler.add_job(
        execute_restore_process, 
        args=[task], 
        id=f"manual_restore_{task_id}_{int(datetime.now().timestamp())}", 
        name=f"Manual Restore: {task['name']}"
    )
    log_to_app(f"Ręczne przywracanie zadania ID {task_id} dodane do kolejki wątków.")
    return {"message": "Przywracanie przekazane do kolejki wykonawczej."}

@app.get("/api/tasks/{task_id}/logs", dependencies=[Depends(verify_api_key)])
def get_task_logs(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Brak zadania")
        
    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    
    if not os.path.exists(task_log_dir):
        return {"logs": "Brak logów dla tego zadania. Nie zostało jeszcze uruchomione."}
        
    try:
        # Pobieramy listę wszystkich plików .log w folderze zadania
        log_files = [os.path.join(task_log_dir, f) for f in os.listdir(task_log_dir) if f.endswith(".log")]
        if not log_files:
            return {"logs": "Brak plików logów w katalogu zadania."}
            
        # Sortujemy po czasie modyfikacji, aby wziąć najnowszy log
        latest_log_path = max(log_files, key=os.path.getmtime)
        
        # Odczytujemy ostatnie 200 linii logu, żeby nie przeciążyć przeglądarki olbrzymim plikiem
        with open(latest_log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            # Wycinamy ostatnie 200 linii (możesz zwiększyć wg uznania)
            last_lines = lines[-200:] if len(lines) > 200 else lines
            log_content = "".join(last_lines)
            
        return {
            "filename": os.path.basename(latest_log_path),
            "logs": log_content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu logów: {str(e)}")

@app.get("/api/browse", dependencies=[Depends(verify_api_key)])
def browse_folder(path: str = ""):
    full_path = os.path.normpath(os.path.join(BASE_STORAGE, path.lstrip("/")))
    if not full_path.startswith(BASE_STORAGE) or not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Brak katalogu")
    try:
        directories = [{"name": entry.name, "path": f"/{os.path.relpath(entry.path, BASE_STORAGE)}"} 
                       for entry in os.scandir(full_path) if entry.is_dir()]
        directories.sort(key=lambda x: x["name"].lower())
        return {"current_path": path, "directories": directories}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    
# --- ENDPOINTY LOGOWANIA I REJESTRACJI ---

@app.post("/api/auth/login")
def login(credentials: LoginSchema):
    config = get_all_tasks()
    users = config.get("users", [])
    
    # 1. Sprawdzamy czy użytkownik istnieje w pliku config.json
    user = next((u for u in users if u["username"] == credentials.username), None)
    
    # 2. Jeśli baza jest pusta, a ktoś loguje się na domyślnego admina z .env
    if not user and credentials.username == ADMIN_USERNAME:
        # Sprawdzamy hasło wprost z .env
        if credentials.password == ADMIN_PASSWORD:
            token = jwt.encode({"username": ADMIN_USERNAME}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": ADMIN_USERNAME}
        raise HTTPException(status_code=400, detail="Nieprawidłowe hasło administratora.")
        
    # 3. Stały użytkownik z bazy (porównujemy zahaszowane hasło)
    if user:
        password_bytes = credentials.password.encode('utf-8')
        hashed_bytes = user["password"].encode('utf-8')
        if bcrypt.checkpw(password_bytes, hashed_bytes):
            token = jwt.encode({"username": user["username"]}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": user["username"]}
            
    raise HTTPException(status_code=400, detail="Nieprawidłowy login lub hasło.")

@app.post("/api/auth/register")
def register(credentials: RegisterSchema):
    if DISABLE_REGISTRATION:
        raise HTTPException(status_code=403, detail="Rejestracja nowych kont jest zablokowana przez administratora.")
        
    config = get_all_tasks()
    config.setdefault("users", [])
    
    if any(u["username"] == credentials.username for u in config["users"]):
        raise HTTPException(status_code=400, detail="Użytkownik o takiej nazwie już istnieje.")
        
    # Haszujemy hasło przed zapisem do pliku JSON
    hashed_password = bcrypt.hashpw(credentials.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = {
        "username": credentials.username,
        "password": hashed_password
    }
    config["users"].append(new_user)
    save_config(config)
    
    return {"message": "Konto zarejestrowane pomyślnie."}