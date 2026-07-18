import os
import json
import subprocess
import urllib.request
import bcrypt
import jwt
import time
import logging
import smtplib
import shutil

from logging.handlers import RotatingFileHandler
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

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication  # Potrzebne do załącznika

app = FastAPI(title="Docker Backup Manager API")

# Pobieramy nowe zmiennes z .env
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
DISABLE_REGISTRATION = os.getenv("DISABLE_REGISTRATION", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-me")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

print(f"DEBUG AUTH -> USER: {ADMIN_USERNAME}, PASS: {ADMIN_PASSWORD}, REG_DISABLED: {DISABLE_REGISTRATION}")

class LoginSchema(BaseModel):
    username: str
    password: str

class RegisterSchema(BaseModel):
    username: str
    password: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # W sieci lokalnej pozwalamy na dostęp z dowolnego źródła
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_PATH = "/app/config/config.json"
RCLONE_CONFIG_PATH = "/app/config/rclone.conf"
BASE_STORAGE = "/storage"
LOGS_BASE_DIR = "/app/logs/tasks"
APP_LOG_PATH = "/app/logs/app.log"

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
executors = {
    'default': ThreadPoolExecutor(max_workers=1)
}
scheduler = BackgroundScheduler(executors=executors)

# Przechowuje referencje do uruchomionych procesów systemowych {task_id: subprocess.Popen}
active_backup_processes = {}

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
    custom_flags: Optional[List[str]] = []  # <-- NOWE POLE NA FLAGI PER ZADANIE
    next_task_id: Optional[int] = None  # <-- NOWE POLE: ID następnego zadania (np. 3)
    # --- NOWE POLA E-MAIL ---
    email_enabled: bool = False
    email_recipients: Optional[str] = ""
    email_level: str = "wszystkie"  # "wszystkie", "bledy_i_onedrive", "tylko_bledy"

# --- FUNKCJE POMOCNICZE ---
def log_to_app(message: str):
    os.makedirs(os.path.dirname(APP_LOG_PATH), exist_ok=True)
    logger = logging.getLogger("AppLogger")
    
    if not logger.handlers:
        handler = RotatingFileHandler(APP_LOG_PATH, maxBytes=5*1024*1024, backupCount=7, encoding="utf-8")
        formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    logger.info(message)

def send_notification(task_name: str, status: str, discord_url: str = None, ntfy_url: str = None, skipped_files: list = None):
    emoji = "✅" if status in ["OK", "SUKCES"] else "❌"
    
    # Podstawowa wiadomość
    msg = f"{emoji} Zadanie '{task_name}' zakończyło się statusem: {status}."
    
    # Jeśli mamy pominięte pliki, doklejamy je do wiadomości na Discorda
    if skipped_files:
        msg += "\n\n⚠️ **Wykryto zbyt długie ścieżki (Pominięte przez OneDrive - limit 400 znaków):**"
        for file_path in skipped_files[:10]:  # Pokazujemy max 10 pierwszych, żeby nie zatkać Discorda
            msg += f"\n• `{file_path}`"
        if len(skipped_files) > 10:
            msg += f"\n... i {len(skipped_files) - 10} więcej. Sprawdź pełny log zadania."

    if discord_url and discord_url not in ["string", "null", "None", ""]:
        try:
            payload = json.dumps({"content": msg}).encode("utf-8")
            req = urllib.request.Request(
                discord_url, 
                data=payload, 
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0"
                }
            )
            with urllib.request.urlopen(req) as res: pass
        except Exception as e: log_to_app(f"Błąd powiadomienia Discord: {str(e)}")

    # ntfy (prostszas wersja, bez markdowna)
    if ntfy_url and ntfy_url not in ["string", "null", "None", ""]:
        try:
            ntfy_msg = msg.replace("**", "").replace("`", "")
            payload = ntfy_msg.encode("utf-8")
            req = urllib.request.Request(
                ntfy_url, 
                data=payload, 
                headers={
                    "Title": f"Backup: {task_name}",
                    "User-Agent": "Mozilla/5.0"
                }
            )
            with urllib.request.urlopen(req) as res: pass
        except Exception as e: log_to_app(f"Błąd powiadomienia ntfy: {str(e)}")

def send_email_notification(task_name: str, status: str, recipients_str: str, skipped_files: list = None, log_file_path: str = None):
    if not SMTP_USER or not SMTP_PASS or not recipients_str:
        log_to_app("E-mail ostrzeżenie: Brak konfiguracji SMTP lub brak odbiorców.")
        return

    try:
        recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
        if not recipients:
            return

        emoji = "✅" if status in ["OK", "SUKCES"] else "❌"
        
        msg = MIMEMultipart()
        msg["From"] = f"Docker Backup Manager <{SMTP_USER}>"
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = f"{emoji} Backup: {task_name} - Status: {status}"

        # --- Podstawowa treść maila ---
        body = f"Zadanie kopii zapasowej '{task_name}' zakończyło się ze statusem: {status}.\n"
        body += f"Czas raportu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        if skipped_files:
            body += "⚠️ Wykryto pliki z pominiętymi zbyt długimi ścieżkami (OneDrive):\n"
            for file_path in skipped_files:
                body += f"- {file_path}\n"
            body += "\n"

        # --- SEKCJA PRZYGOTOWANIA ZAŁĄCZNIKA Z LOGAMI ERROR ---
        error_content = ""
        if log_file_path and os.path.exists(log_file_path):
            error_lines = []
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "ERROR" in line:
                            # --- BEZPIECZNIK: Ignoruj standardowe ostrzeżenia rclone o IO errors ---
                            if "not deleting files as there were IO errors" in line:
                                continue
                            if "not deleting directories as there were IO errors" in line:
                                continue
                            
                            error_lines.append(line.strip())
            except Exception as log_err:
                body += f"[Błąd podczas odczytu pliku logów do załącznika: {str(log_err)}]\n"

            if error_lines:
                # Tworzymy treść pliku tekstowego ze wszystkimi błędami
                error_content = f"RAPORT BŁĘDÓW DLA ZADANIA: {task_name}\n"
                error_content += f"Status końcowy: {status}\n"
                error_content += f"Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                error_content += "--------------------------------------------------\n\n"
                for err_line in error_lines:
                    error_content += f"{err_line}\n"
                
                body += f"🚨 Znaleziono błędy w logach ({len(error_lines)} linii ERROR). Pełna lista znajduje się w załączniku.\n"
            else:
                body += "ℹ️ W pliku logów nie znaleziono żadnych wpisów zawierających 'ERROR'.\n"

        # Dołączamy główną treść wiadomości
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Jeśli znaleziono błędy, generujemy i dołączamy plik .txt
        if error_content:
            attachment = MIMEApplication(error_content.encode("utf-8"), _subtype="txt")
            # Bezpieczna nazwa pliku bez spacji i dziwnych znaków
            safe_task_name = "".join(c for c in task_name if c.isalnum() or c in ("-", "_")).rstrip()
            filename = f"bledy_{safe_task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            attachment.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(attachment)

        # Wysyłka SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
            
        log_to_app(f"Powiadomienie e-mail dla zadania '{task_name}' zostało pomyślnie wysłane z załącznikiem.")
    except Exception as e:
        log_to_app(f"Błąd podczas wysyłania powiadomienia e-mail: {str(e)}")

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
        
        # --- BEZPIECZNIK: Ignoruj, jeśli ścieżka lokalna zawiera dwukropek (to na pewno chmura) ---
        if ":" in trash_base:
            log_to_app(
                f"Błędna ścieżka lokalna w zadaniu '{task['name']}': {trash_base}"
            )
            return
            
        if not os.path.exists(trash_base):
            return
        try:
            subdirs = [os.path.join(trash_base, d) for d in os.listdir(trash_base)]
            subdirs = [d for d in subdirs if os.path.isdir(d)]
            subdirs.sort()
            while len(subdirs) > retention_limit:
                oldest_folder = subdirs.pop(0)
                #subprocess.run(["rm", "-rf", oldest_folder])
                #log_to_app(f"Retencja lokalna: Usunięto najstarszy folder kosza: {oldest_folder}")
        #except Exception as e:
            #log_to_app(f"Błąd czyszczenia kosza lokalnego: {str(e)}")
                try:
                    shutil.rmtree(oldest_folder)
                    log_to_app(f"Retencja lokalna: Usunięto najstarszy folder kosza: {oldest_folder}")
                except Exception as rm_err:
                    log_to_app(f"Błąd retencji lokalnej podczas usuwania {oldest_folder}: {str(rm_err)}")
        except Exception as e:
            log_to_app(f"Błąd odczytu katalogu kosza lokalnego: {str(e)}")

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
                
                cmd_purge = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "purge", full_remote_trash_path]
                result = subprocess.run(cmd_purge, capture_output=True, text=True)
                
                if result.returncode == 0:
                    log_to_app(f"Retencja chmury: Usunięto najstarszy folder kosza: {full_remote_trash_path}")
                else:
                    clean_error = result.stderr.strip() if result.stderr else "Nieznany błąd"
                    log_to_app(f"Błąd retencji chmury dla {full_remote_trash_path}: {clean_error}")
        except Exception as e:
            log_to_app(f"Błąd czyszczenia kosza w chmurze (silnik): {str(e)}")
                #subprocess.run(["rclone", f"--config={RCLONE_CONFIG_PATH}", "purge", full_remote_trash_path])
                #log_to_app(f"Retencja chmury: Usunięto najstarszy folder kosza: {full_remote_trash_path}")
        #except Exception as e:
            #log_to_app(f"Błąd czyszczenia kosza w chmurze: {str(e)}")

def clean_all_trash_folders_cron():
    log_to_app("Harmonogram: Uruchomiono nocne czyszczenie kosza dla wszystkich zadań.")
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if task.get("enabled", True) and task.get("retention_days", 0) > 0:
            clean_old_trash_folders(task)
            
    # --- NOWA SEKCJA: CZYSZCZENIE LOGÓW STARSZYCH NIŻ 365 DNI ---
    log_to_app("Harmonogram: Uruchomiono czyszczenie logów starszych niż 365 dni.")
    now = time.time()
    cutoff = now - (365 * 24 * 60 * 60)
    
    if os.path.exists(LOGS_BASE_DIR):
        for root, dirs, files in os.walk(LOGS_BASE_DIR):
            for file in files:
                if file.endswith(".log"):
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < cutoff:
                        try:
                            os.remove(file_path)
                            log_to_app(f"Rotacja logów: Usunięto stary plik logu: {file}")
                        except Exception as e:
                            pass

# --- SILNIK BACKUPU ---
def execute_backup_process(task_id: int):
    # 1. Pobieramy najświeższy config z bazy na samym starcie wątku
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    
    if not task:
        log_to_app(f"Błąd uruchomienia: Zadanie o ID {task_id} nie istnieje w bazie config.json.")
        return

    # 2. Ustawiamy status RUNNING
    for t in config.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "RUNNING"
            break
    save_config(config)
    
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
            
        global_config = get_all_tasks()
        settings = global_config.get("settings", {})
        
        rclone_flags = task.get("custom_flags")
        if rclone_flags is None:
            rclone_flags = settings.get("rclone_flags", ["--buffer-size=16M", "--transfers=2"])
        
        cmd.extend(rclone_flags)
            
        for ex in task.get("exclude", []):
            if ex: cmd.extend(["--exclude", ex])
        cmd.extend([task["source"], task["destination"], "-v"])
        
    else:
        return

    try:
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== START BACKUP ({task['type'].upper()}): {task['name']} ===\n")
            log_file.write(f"Komenda: {' '.join(cmd)}\n\n")
            log_file.flush()
            
            process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, text=True)
            #process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, text=True, cwd="/tmp") #dodanie , cwd="/tmp")
            active_backup_processes[task_id] = process  # Używamy bezpiecznego task_id
            process.wait()
            
        active_backup_processes.pop(task_id, None)  # Używamy bezpiecznego task_id
            
        # Sprawdzamy czy zadanie nie zostało zatrzymane przez użytkownika
        current_config = get_all_tasks()
        task_in_db = next((t for t in current_config.get("tasks", []) if t["id"] == task_id), None)
            
        if task_in_db and task_in_db.get("status") == "Zatrzymane":
            log_to_app(f"Zadanie '{task['name']}' zostało przerwane na żądanie użytkownika.")
            return
                
        final_status = "OK" if process.returncode == 0 else "Błąd"
        skipped_onedrive_files = []

        if task["type"] == "cloud" and final_status == "Błąd" and os.path.exists(log_file_path):
            try:
                has_other_errors = False
                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "ERROR :" in line:
                            if (
                                "not deleting directories as there were IO errors" in line or 
                                "not deleting files as there were IO errors" in line or 
                                "Can't retry any of the errors" in line
                            ):
                                continue

                            if "pathIsTooLong" in line or "The specified file or folder name is too long" in line:
                                parts = line.split("ERROR :")
                                if len(parts) > 1:
                                    file_part = parts[1].split(":")[0].strip()
                                    if file_part and file_part not in skipped_onedrive_files:
                                        skipped_onedrive_files.append(file_part)
                            else:
                                has_other_errors = True
                
                if len(skipped_onedrive_files) > 0 and not has_other_errors:
                    log_to_app(f"Zadanie '{task['name']}': Wykryto {len(skipped_onedrive_files)} błędów typu 'pathIsTooLong'. Brak innych błędów. Status złagodzony do 'OK'.")
                    final_status = "OK"
            except Exception as parse_error:
                log_to_app(f"Błąd podczas parsowania logu OneDrive: {str(parse_error)}")

        # Zapisujemy finalny status
        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task_id:
                t["status"] = final_status
                break
        save_config(config)
            
        log_to_app(f"Zadanie {task['name']} zakończone status: {final_status}.")
        
        # ==================== POPRAWIONA SEKCJA POWIADOMIEŃ ====================
        # Wysyłamy Discorda gdy jest Błąd LUB gdy jest OK, ale rclone pominął za długie ścieżki
        try:
            send_notification(
                task["name"], 
                final_status, 
                discord_url=task.get("discord_webhook"), 
                ntfy_url=task.get("ntfy_url"),
                skipped_files=skipped_onedrive_files if len(skipped_onedrive_files) > 0 else None
            )
        except Exception as notify_err:
            log_to_app(f"Błąd wysyłania powiadomienia (Discord/Ntfy): {str(notify_err)}")
        # =======================================================================

        # 2. Powiadomienia E-mail (Z wyciąganiem linii ERROR z logu konkretnego zadania)
        if task.get("email_enabled", False) and task.get("email_recipients"):
            email_level = task.get("email_level", "tylko_bledy")
            should_send_email = False

            if email_level == "wszystkie":
                should_send_email = True
            elif email_level == "bledy_i_onedrive":
                if final_status == "Błąd" or len(skipped_onedrive_files) > 0:
                    should_send_email = True
            elif email_level == "tylko_bledy":
                if final_status == "Błąd":
                    should_send_email = True

            if should_send_email:
                # Przekazujemy 'log_file_path', który został utworzony na początku tej funkcji
                send_email_notification(
                    task["name"],
                    final_status,
                    task["email_recipients"],
                    skipped_files=skipped_onedrive_files if len(skipped_onedrive_files) > 0 else None,
                    log_file_path=log_file_path  # <-- TUTAJ przekazujemy precyzyjny log zadania
                )
        # ============================================================
            
        if final_status in ["OK", "SUCCESS"]:
            clean_old_trash_folders(task)
            
            # Autouruchamianie zadania zależnego (łańcuch)
            next_id = task.get("next_task_id")
            if next_id:
                all_tasks_config = get_all_tasks()
                next_task = next((t for t in all_tasks_config.get("tasks", []) if t["id"] == next_id), None)
                
                if next_task:
                    log_to_app(f"Łańcuch zadań: Zadanie '{task['name']}' zakończone sukcesem. Automatyczne wywoływanie kolejnego zadania ID {next_id}: '{next_task['name']}'.")
                    
                    scheduler.add_job(
                        execute_backup_process, 
                        args=[next_task["id"]], 
                        id=f"chained_{next_id}_{int(datetime.now().timestamp())}", 
                        name=f"Chained Run: {next_task['name']}",
                        misfire_grace_time=None
                    )
                else:
                    log_to_app(f"Łańcuch zadań ostrzeżenie: Zadanie '{task['name']}' wskazuje na następne ID {next_id}, ale takie zadanie nie istnieje w config.json.")

    except Exception as e:
        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task_id:
                t["status"] = "Błąd"
                break
        save_config(config)
        log_to_app(f"Krytyczny błąd {task.get('name', f'ID {task_id}')}: {str(e)}")

# --- SILNIK RESTORE ---
def execute_restore_process(task_id: int):
    # Pobieramy najświeższą konfigurację zadania z pliku JSON
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    
    if not task:
        log_to_app(f"Błąd przywracania: Zadanie o ID {task_id} nie istnieje w bazie config.json.")
        return

    # Od tego miejsca kod pozostaje niemal bez zmian, korzystając ze zmiennej 'task'
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
        
        # --- POPRAWKA: WSTRZYKIWANIE DYNAMICZNYCH FLAG DO PROCESU RESTORE ---
        global_config = get_all_tasks()
        settings = global_config.get("settings", {})
        rclone_flags = task.get("custom_flags")
        if rclone_flags is None:
            rclone_flags = settings.get("rclone_flags", ["--buffer-size=16M", "--transfers=2"])
            
        # Wstrzykujemy flagi optymalizacyjne zaraz po słowie 'copy'
        cmd = cmd[:3] + rclone_flags + cmd[3:]
    else:
        return

    try:
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== START RESTORE: {task['name']} ===\n")
            log_file.write(f"Komenda: {' '.join(cmd)}\n\n")
            log_file.flush()
            process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True)
            #process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True, cwd="/tmp") #dodanie , cwd="/tmp")
            
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
            execute_backup_process, trigger=trigger, args=[task["id"]],
            id=str(task["id"]), name=task["name"], replace_existing=True,
            misfire_grace_time=None
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
    # --- NOWOŚĆ: CZYSZCZENIE STATUSÓW RUNNING PO RESTARCIE ---
    config = get_all_tasks()
    status_changed = False
    for task in config.get("tasks", []):
        if task.get("status") == "RUNNING":
            task["status"] = "Błąd"
            log_to_app(f"System: Wykryto wiszące zadanie ID {task['id']} ('{task['name']}') ze statusu RUNNING. Zresetowano do pozycji 'Błąd' po restarcie kontenera.")
            status_changed = True
    if status_changed:
        save_config(config)

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
    
    if task.type == "local" and not os.path.exists(task.source):
        raise HTTPException(status_code=400, detail=f"Brak katalogu: {task.source}")
    #to wymaga poprawy?
    #elif task.type == "cloud" and not os.path.exists(task.destination) and not task.destination.startswith("http"):
    #    os.makedirs(task.destination, exist_ok=True)
        
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
    
    if fields.type == "local" and not os.path.exists(fields.source):
        raise HTTPException(status_code=400, detail="Brak źródła")
    #to wymaga poprawy?
    #elif fields.type == "cloud" and not os.path.exists(fields.destination):
    #    os.makedirs(fields.destination, exist_ok=True)
    
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

@app.post("/api/tasks/{task_id}/run", dependencies=[Depends(verify_api_key)])
def run_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Brak zadania")
    
    scheduler.add_job(
        execute_backup_process,
        args=[task_id],
        id=f"manual_{task_id}_{int(datetime.now().timestamp())}",
        name=f"Manual Run: {task['name']}",
        misfire_grace_time=None
    )
    log_to_app(f"Ręczne wywołanie zadania ID {task_id} dodane do kolejki wątków.")
    return {"message": "Zadanie przekazane do kolejki wykonawczej (wykonywanie jedno po drugim)."}

@app.post("/api/tasks/{task_id}/stop", dependencies=[Depends(verify_api_key)])
def stop_task(task_id: int):
    # Pobieramy konfigurację zadania, aby mieć dostęp do jego nazwy oraz webhooków powiadomień
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: 
        raise HTTPException(status_code=404, detail="Brak zadania")

    process = active_backup_processes.get(task_id)
    
    if process:
        try:
            log_to_app(f"Żądanie zatrzymania zadania ID {task_id}. Wysyłanie sygnału zakończenia.")
            
            # 1. Wysyłamy dedykowaną notyfikację na Discord/Ntfy ZAMIAST standardowej
            send_notification(
                task["name"], 
                "Zatrzymane na żądanie 🛑", 
                discord_url=task.get("discord_webhook"), 
                ntfy_url=task.get("ntfy_url")
            )
            
            # 2. Ustawiamy status "Zatrzymane" w bazie danych
            config = get_all_tasks()
            for t in config.get("tasks", []):
                if t["id"] == task_id:
                    t["status"] = "Zatrzymane"
                    break
            save_config(config)
            
            # 3. Ubijamy proces systemowy
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                
            return {"message": "Zadanie zostało wymuszenie zatrzymane."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Błąd podczas zatrzymywania procesu: {str(e)}")
            
    # Jeśli fizycznego procesu nie ma w pamięci, ale status w pliku JSON wisiał jako RUNNING
    config = get_all_tasks()
    for t in config.get("tasks", []):
        if t["id"] == task_id and t["status"] == "RUNNING":
            t["status"] = "Zatrzymane"
            save_config(config)
            log_to_app(f"Ręczne zresetowanie zawieszonego statusu RUNNING dla zadania ID {task_id}.")
            send_notification(
                task["name"], 
                "Zatrzymane na żądanie 🛑", 
                discord_url=task.get("discord_webhook"), 
                ntfy_url=task.get("ntfy_url")
            )
            return {"message": "Proces nie był aktywny. Status zadania zresetowano do pozycji 'Zatrzymane'."}
            
    raise HTTPException(status_code=400, detail="To zadanie nie jest aktualnie uruchomione.")

@app.post("/api/tasks/{task_id}/restore", dependencies=[Depends(verify_api_key)])
def restore_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Brak zadania")
    if not task.get("restore_enabled", False):
        raise HTTPException(status_code=400, detail="Restore jest zablokowane w konfiguracji.")
        
    scheduler.add_job(
        execute_restore_process, 
        args=[task_id],  # <-- POPRAWKA: Przekazujemy tylko task_id
        id=f"manual_restore_{task_id}_{int(datetime.now().timestamp())}", 
        name=f"Manual Restore: {task['name']}",
        misfire_grace_time=None
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
        log_files = [os.path.join(task_log_dir, f) for f in os.listdir(task_log_dir) if f.endswith(".log")]
        if not log_files:
            return {"logs": "Brak plików logów w katalogu zadania."}
            
        latest_log_path = max(log_files, key=os.path.getmtime)
        
        with open(latest_log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
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
    
    user = next((u for u in users if u["username"] == credentials.username), None)
    
    if not user and credentials.username == ADMIN_USERNAME:
        if credentials.password == ADMIN_PASSWORD:
            token = jwt.encode({"username": ADMIN_USERNAME}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": ADMIN_USERNAME}
        raise HTTPException(status_code=400, detail="Nieprawidłowe hasło administratora.")
        
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
        
    hashed_password = bcrypt.hashpw(credentials.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = {
        "username": credentials.username,
        "password": hashed_password
    }
    config["users"].append(new_user)
    save_config(config)
    
    return {"message": "Konto zarejestrowane pomyślnie."}