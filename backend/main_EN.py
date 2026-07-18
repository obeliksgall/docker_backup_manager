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
from typing import Optional, List, Literal  # <-- DODANO Literal DO WALIDACJI

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication  # Potrzebne do załącznika

app = FastAPI(title="Docker Backup Manager API")

# Environment variables
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
    allow_origins=["*"],
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
            detail="Access Denied: Invalid or missing API Key (X-API-Key)."
        )
    return api_key

# --- TASK QUEUE CONFIGURATION ---
executors = {
    'default': ThreadPoolExecutor(max_workers=1)
}
scheduler = BackgroundScheduler(executors=executors)

# Process tracking map
active_backup_processes = {}

# --- DATA VALIDATION SCHEMA ---
class TaskSchema(BaseModel):
    name: str
    source: str
    destination: str
    type: Literal["local", "cloud"]              # <-- ŚCISŁA WALIDACJA TYPU #type: str                  # "local" or "cloud"
    mode: Literal["mirror", "copy", "move"]       # <-- ŚCISŁA WALIDACJA TRYBU #mode: str                  # "mirror", "incremental", "move"
    schedule: str              # Cron expression, e.g., "0 3 * * *"
    enabled: bool = True       # Active in schedule
    restore_enabled: bool = False
    exclude: List[str] = []
    retention_days: int = 0    # 0 = disabled
    discord_webhook: Optional[str] = None
    ntfy_url: Optional[str] = None
    custom_flags: Optional[List[str]] = []
    next_task_id: Optional[int] = None
    # --- NOWE POLA E-MAIL ---
    email_enabled: bool = False
    email_recipients: Optional[str] = ""
    email_level: Literal["wszystkie", "bledy_i_onedrive", "tylko_bledy"] = "wszystkie" # <-- ZABEZPIECZONY LEVEL #email_level: str = "wszystkie"  # "wszystkie", "bledy_i_onedrive", "tylko_bledy"

# --- HELPER FUNCTIONS ---
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
    emoji = "✅" if status in ["OK", "SUCCESS"] else "❌"
    msg = f"{emoji} Task '{task_name}' finished with status: {status}."
    
    if skipped_files:
        msg += "\n\n⚠️ **Paths too long detected (Skipped by OneDrive - 400 characters limit):**"
        for file_path in skipped_files[:10]:
            msg += f"\n• `{file_path}`"
        if len(skipped_files) > 10:
            msg += f"\n... and {len(skipped_files) - 10} more. Check the full task log."

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
        except Exception as e: log_to_app(f"Discord notification error: {str(e)}")

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
        except Exception as e: log_to_app(f"Ntfy notification error: {str(e)}")

def send_email_notification(task_name: str, status: str, recipients_str: str, skipped_files: list = None, log_file_path: str = None):
    if not SMTP_USER or not SMTP_PASS or not recipients_str:
        log_to_app("Email warning: Missing SMTP configuration or missing recipients.")
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
        body = f"Backup task '{task_name}' completed with status: {status}.\n"
        body += f"Report time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        if skipped_files:
            body += "⚠️ Files with paths that were too long were skipped. (OneDrive):\n"
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
                error_content = f"ERROR REPORT FOR THE TASK: {task_name}\n"
                error_content += f"Final status: {status}\n"
                error_content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                error_content += "--------------------------------------------------\n\n"
                for err_line in error_lines:
                    error_content += f"{err_line}\n"
                
                body += f"🚨 Errors found in the logs. ({len(error_lines)} line ERROR). The full list is in the attachment..\n"
            else:
                body += "ℹ️ No entries containing 'ERROR' were found in the log file.\n"

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
            
        log_to_app(f"Email notification for the task '{task_name}' was successfully sent with an attachment.")
    except Exception as e:
        log_to_app(f"Error sending email notification: {str(e)}")

def save_config(data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_all_tasks():
    if not os.path.exists(CONFIG_PATH):
        return {"tasks": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# --- TRASH RETENTION SERVICE ---
def clean_old_trash_folders(task: dict):
    retention_limit = task.get("retention_days", 0)
    if retention_limit <= 0:
        return

    log_to_app(f"Starting trash cleanup for task '{task['name']}' (Retention limit: {retention_limit}).")

    if task["type"] == "local":
        trash_base = task["destination"].rstrip("/") + "-trash"
        
        # --- BEZPIECZNIK: Ignoruj, jeśli ścieżka lokalna zawiera dwukropek (to na pewno chmura) ---
        if ":" in trash_base:
            log_to_app(
                f"Invalid local path in the task '{task['name']}': {trash_base}"
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
                #log_to_app(f"Local Retention: Removed oldest trash folder: {oldest_folder}")
        #except Exception as e:
            #log_to_app(f"Local retention error: {str(e)}")
                try:
                    shutil.rmtree(oldest_folder)
                    log_to_app(f"Local Retention: Removed oldest trash folder: {oldest_folder}")
                except Exception as rm_err:
                    log_to_app(f"Local retention error during deletion {oldest_folder}: {str(rm_err)}")
        except Exception as e:
            log_to_app(f"Error reading local Trash directory: {str(e)}")

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
                    log_to_app(f"Cloud Retention: Removed oldest trash folder: {full_remote_trash_path}")
                else:
                    clean_error = result.stderr.strip() if result.stderr else "Nieznany błąd"
                    log_to_app(f"Cloud retention error for {full_remote_trash_path}: {clean_error}")
        except Exception as e:
            log_to_app(f"Error clearing cloud trash (engine): {str(e)}")
                #subprocess.run(["rclone", f"--config={RCLONE_CONFIG_PATH}", "purge", full_remote_trash_path])
                #log_to_app(f"Retencja chmury: Usunięto najstarszy folder kosza: {full_remote_trash_path}")
        #except Exception as e:
            #log_to_app(f"Błąd czyszczenia kosza w chmurze: {str(e)}")

def clean_all_trash_folders_cron():
    log_to_app("Scheduler: Running nightly trash cleanup for all tasks.")
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if task.get("enabled", True) and task.get("retention_days", 0) > 0:
            clean_old_trash_folders(task)
            
    log_to_app("Scheduler: Rotating log files older than 365 days.")
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
                            log_to_app(f"Log Rotation: Deleted old log file: {file}")
                        except Exception as e:
                            pass

# --- BACKUP ENGINE ---
def execute_backup_process(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    
    if not task:
        log_to_app(f"Execution Error: Task ID {task_id} does not exist in config.json.")
        return

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
    
    log_to_app(f"Launching task ({task['type']} - {task.get('mode', 'mirror')}): {task['name']}.")
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
            log_file.write(f"Command: {' '.join(cmd)}\n\n")
            log_file.flush()
            
            process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, text=True)
            #process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, text=True, cwd="/tmp")
            active_backup_processes[task_id] = process
            process.wait()
            
        active_backup_processes.pop(task_id, None)
            
        current_config = get_all_tasks()
        task_in_db = next((t for t in current_config.get("tasks", []) if t["id"] == task_id), None)
            
        if task_in_db and task_in_db.get("status") in ["Stopped", "Zatrzymane", "STOPPED"]:
            log_to_app(f"Task '{task['name']}' was stopped by user request.")
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
                    log_to_app(f"Task '{task['name']}': Detected {len(skipped_onedrive_files)} 'pathIsTooLong' errors. No other failures. Status mitigated to 'OK'.")
                    final_status = "OK"
            except Exception as parse_error:
                log_to_app(f"Error parsing OneDrive log: {str(parse_error)}")

        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task_id:
                t["status"] = final_status
                break
        save_config(config)
            
        log_to_app(f"Task {task['name']} completed with status: {final_status}.")
        
        # ==================== POPRAWIONA SEKCJA POWIADOMIEŃ ====================
        # Wysyłamy Discorda gdy jest Błąd LUB gdy jest OK, ale rclone pominął za długie ścieżki
        #if final_status == "Błąd" or (final_status == "OK" and len(skipped_onedrive_files) > 0):
        try:
            send_notification(
                task["name"], 
                final_status, 
                discord_url=task.get("discord_webhook"), 
                ntfy_url=task.get("ntfy_url"),
                skipped_files=skipped_onedrive_files if len(skipped_onedrive_files) > 0 else None
            )
        except Exception as notify_err:
            log_to_app(f"Error sending notification (Discord/Ntfy): {str(notify_err)}")
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
            
            next_id = task.get("next_task_id")
            if next_id:
                all_tasks_config = get_all_tasks()
                next_task = next((t for t in all_tasks_config.get("tasks", []) if t["id"] == next_id), None)
                
                if next_task:
                    log_to_app(f"Task Chain: Task '{task['name']}' finished successfully. Automatically calling dependent task ID {next_id}: '{next_task['name']}'.")
                    
                    scheduler.add_job(
                        execute_backup_process, 
                        args=[next_task["id"]], 
                        id=f"chained_{next_id}_{int(datetime.now().timestamp())}", 
                        name=f"Chained Run: {next_task['name']}",
                        misfire_grace_time=None
                    )
                else:
                    log_to_app(f"Task Chain Warning: Task '{task['name']}' points to next ID {next_id}, but that task does not exist in config.json.")

    except Exception as e:
        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task_id:
                t["status"] = "Błąd"
                break
        save_config(config)
        log_to_app(f"Critical error on {task.get('name', f'ID {task_id}')}: {str(e)}")

# --- RESTORE ENGINE ---
def execute_restore_process(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    
    if not task:
        log_to_app(f"Restore Error: Task ID {task_id} does not exist in config.json.")
        return

    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_RESTORE")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")
    
    log_to_app(f"Starting RESTORE procedure for task: {task['name']}.")
    
    if task["type"] == "local":
        os.makedirs(task["source"], exist_ok=True)
        dest_path = task["destination"].rstrip("/") + "/"
        cmd = ["rsync", "-rtv", dest_path, task["source"]]
    elif task["type"] == "cloud":
        cmd = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "copy", task["destination"], task["source"], "-v"]
        
        global_config = get_all_tasks()
        settings = global_config.get("settings", {})
        rclone_flags = task.get("custom_flags")
        if rclone_flags is None:
            rclone_flags = settings.get("rclone_flags", ["--buffer-size=16M", "--transfers=2"])
            
        cmd = cmd[:3] + rclone_flags + cmd[3:]
    else:
        return

    try:
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== START RESTORE: {task['name']} ===\n")
            log_file.write(f"Command: {' '.join(cmd)}\n\n")
            log_file.flush()
            process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True)
            #process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True, cwd="/tmp")
            
        status = "SUKCES" if process.returncode == 0 else "BŁĄD"
        log_to_app(f"Restore of {task['name']} completed: {status}.")
        send_notification(f"RESTORE: {task['name']}", status, discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
    except Exception as e:
        log_to_app(f"Restore operation failed for {task['name']}: {str(e)}")

# --- SCHEDULER LIFECYCLE BINDINGS ---
def add_task_to_scheduler(task: dict):
    if not task.get("enabled", True):
        if scheduler.get_job(str(task["id"])):
            scheduler.remove_job(str(task["id"]))
            log_to_app(f"Removed from scheduler (disabled): '{task['name']}'")
        return
    try:
        trigger = CronTrigger.from_crontab(task["schedule"])
        scheduler.add_job(
            execute_backup_process, trigger=trigger, args=[task["id"]],
            id=str(task["id"]), name=task["name"], replace_existing=True,
            misfire_grace_time=None
        )
        log_to_app(f"Registered in scheduler: '{task['name']}' ({task['schedule']})")
    except Exception as e:
        log_to_app(f"Scheduler registration error for '{task['name']}': {str(e)}")

def load_all_tasks_into_scheduler():
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if "mode" not in task: task["mode"] = "mirror"
        add_task_to_scheduler(task)
        
    scheduler.add_job(clean_all_trash_folders_cron, trigger=CronTrigger.from_crontab("15 0 * * *"), id="trash_cleaner", replace_existing=True)

@app.on_event("startup")
def startup_event():
    config = get_all_tasks()
    status_changed = False
    for task in config.get("tasks", []):
        if task.get("status") == "RUNNING":
            task["status"] = "Błąd"
            log_to_app(f"System: Hanging task ID {task['id']} ('{task['name']}') found in RUNNING state. Purged back to 'Błąd' status after container reboot.")
            status_changed = True
    if status_changed:
        save_config(config)

    load_all_tasks_into_scheduler()
    scheduler.start()
    log_to_app("Scheduler engine and trash retention services started successfully (Queue operational).")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

# --- API ENDPOINTS ---
@app.get("/api/tasks", dependencies=[Depends(verify_api_key)])
def get_tasks():
    return get_all_tasks()

@app.post("/api/tasks", dependencies=[Depends(verify_api_key)])
def create_task(task: TaskSchema):
    config = get_all_tasks()
    existing_ids = [t["id"] for t in config.get("tasks", [])]
    new_id = max(existing_ids) + 1 if existing_ids else 1
    
    if task.type == "local" and not os.path.exists(task.source):
        raise HTTPException(status_code=400, detail=f"Directory path does not exist: {task.source}")
    #elif task.type == "cloud" and not os.path.exists(task.destination) and not task.destination.startswith("http"):
    #    os.makedirs(task.destination, exist_ok=True)
        
    new_task = task.dict()
    new_task["id"] = new_id
    new_task["status"] = "New"
    
    config.setdefault("tasks", []).append(new_task)
    save_config(config)
    add_task_to_scheduler(new_task)
    log_to_app(f"Created task: {task.name}")
    return {"task": new_task}

@app.put("/api/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
def update_task(task_id: int, fields: TaskSchema):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    idx = next((i for i, t in enumerate(tasks) if t["id"] == task_id), None)
    
    if idx is None: raise HTTPException(status_code=404, detail="Task not found")
    
    if fields.type == "local" and not os.path.exists(fields.source):
        raise HTTPException(status_code=400, detail="Source path does not exist")
    #elif fields.type == "cloud" and not os.path.exists(fields.destination):
    #    os.makedirs(fields.destination, exist_ok=True)
    
    updated_task = fields.dict()
    updated_task["id"] = task_id
    updated_task["status"] = tasks[idx].get("status", "New")
    
    tasks[idx] = updated_task
    save_config(config)
    add_task_to_scheduler(updated_task)
    log_to_app(f"Updated task ID {task_id}: {fields.name}")
    return {"task": updated_task}

@app.delete("/api/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
def delete_task(task_id: int):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    if not any(t["id"] == task_id for t in tasks): raise HTTPException(status_code=404, detail="Task not found")
    
    config["tasks"] = [t for t in tasks if t["id"] != task_id]
    save_config(config)
    if scheduler.get_job(str(task_id)): scheduler.remove_job(str(task_id))
    log_to_app(f"Deleted task ID {task_id}.")
    return {"message": "Task successfully deleted"}

@app.post("/api/tasks/{task_id}/run", dependencies=[Depends(verify_api_key)])
def run_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    
    scheduler.add_job(
        execute_backup_process,
        args=[task_id],
        id=f"manual_{task_id}_{int(datetime.now().timestamp())}",
        name=f"Manual Run: {task['name']}",
        misfire_grace_time=None
    )
    log_to_app(f"Manual invocation for task ID {task_id} dispatched to the queue thread pool.")
    return {"message": "Task sent to the processing queue pool successfully."}

@app.post("/api/tasks/{task_id}/stop", dependencies=[Depends(verify_api_key)])
def stop_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: 
        raise HTTPException(status_code=404, detail="Task not found")

    process = active_backup_processes.get(task_id)
    
    if process:
        try:
            log_to_app(f"Termination requested for task ID {task_id}. Dispatching kill signal.")
            
            send_notification(
                task["name"], 
                "Zatrzymane na żądanie 🛑", 
                discord_url=task.get("discord_webhook"), 
                ntfy_url=task.get("ntfy_url")
            )
            
            config = get_all_tasks()
            for t in config.get("tasks", []):
                if t["id"] == task_id:
                    t["status"] = "Zatrzymane"
                    break
            save_config(config)
            
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                
            return {"message": "Task forced to terminate successfully."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error stopping backend task thread process: {str(e)}")
            
    config = get_all_tasks()
    for t in config.get("tasks", []):
        if t["id"] == task_id and t["status"] == "RUNNING":
            t["status"] = "Zatrzymane"
            save_config(config)
            log_to_app(f"Manual status reset executed for hanging RUNNING task ID {task_id}.")
            send_notification(
                task["name"], 
                "Zatrzymane na żądanie 🛑", 
                discord_url=task.get("discord_webhook"), 
                ntfy_url=task.get("ntfy_url")
            )
            return {"message": "Process wasn't running inside active memory pool. State purged back to Stopped position."}
            
    raise HTTPException(status_code=400, detail="This task is not currently running.")

@app.post("/api/tasks/{task_id}/restore", dependencies=[Depends(verify_api_key)])
def restore_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    if not task.get("restore_enabled", False):
        raise HTTPException(status_code=400, detail="Restore options are locked within task attributes configuration.")
        
    scheduler.add_job(
        execute_restore_process, 
        args=[task_id], 
        id=f"manual_restore_{task_id}_{int(datetime.now().timestamp())}", 
        name=f"Manual Restore: {task['name']}",
        misfire_grace_time=None
    )
    log_to_app(f"Manual restore request for task ID {task_id} pushed into execution thread pool queue.")
    return {"message": "Restore process dispatched to queue pipeline successfully."}

@app.get("/api/tasks/{task_id}/logs", dependencies=[Depends(verify_api_key)])
def get_task_logs(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    
    if not os.path.exists(task_log_dir):
        return {"logs": "No log assets recorded for this task yet. It has not been run."}
        
    try:
        log_files = [os.path.join(task_log_dir, f) for f in os.listdir(task_log_dir) if f.endswith(".log")]
        if not log_files:
            return {"logs": "No active log files present inside specific folder directory."}
            
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
        raise HTTPException(status_code=500, detail=f"Error reading task runtime log asset: {str(e)}")

@app.get("/api/browse", dependencies=[Depends(verify_api_key)])
def browse_folder(path: str = ""):
    full_path = os.path.normpath(os.path.join(BASE_STORAGE, path.lstrip("/")))
    if not full_path.startswith(BASE_STORAGE) or not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Directory folder path not found")
    try:
        directories = [{"name": entry.name, "path": f"/{os.path.relpath(entry.path, BASE_STORAGE)}"} 
                       for entry in os.scandir(full_path) if entry.is_dir()]
        directories.sort(key=lambda x: x["name"].lower())
        return {"current_path": path, "directories": directories}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# --- AUTHENTICATION ENDPOINTS ---
@app.post("/api/auth/login")
def login(credentials: LoginSchema):
    config = get_all_tasks()
    users = config.get("users", [])
    
    user = next((u for u in users if u["username"] == credentials.username), None)
    
    if not user and credentials.username == ADMIN_USERNAME:
        if credentials.password == ADMIN_PASSWORD:
            token = jwt.encode({"username": ADMIN_USERNAME}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": ADMIN_USERNAME}
        raise HTTPException(status_code=400, detail="Invalid administrator password credentials.")
        
    if user:
        password_bytes = credentials.password.encode('utf-8')
        hashed_bytes = user["password"].encode('utf-8')
        if bcrypt.checkpw(password_bytes, hashed_bytes):
            token = jwt.encode({"username": user["username"]}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": user["username"]}
            
    raise HTTPException(status_code=400, detail="Invalid login username or password.")

@app.post("/api/auth/register")
def register(credentials: RegisterSchema):
    if DISABLE_REGISTRATION:
        raise HTTPException(status_code=403, detail="New user profiles registration is blocked by administrator settings.")
        
    config = get_all_tasks()
    config.setdefault("users", [])
    
    if any(u["username"] == credentials.username for u in config["users"]):
        raise HTTPException(status_code=400, detail="Username profile is already taken.")
        
    hashed_password = bcrypt.hashpw(credentials.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = {
        "username": credentials.username,
        "password": hashed_password
    }
    config["users"].append(new_user)
    save_config(config)
    
    return {"message": "Account created and registered successfully."}