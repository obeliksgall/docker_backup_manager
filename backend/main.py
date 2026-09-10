import os
import re
import json
import subprocess
import urllib.request
import bcrypt
import jwt
import time
import logging
import smtplib
import shutil
import base64
import secrets
import threading
import tempfile
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Optional, List, Literal

from fastapi import FastAPI, HTTPException, Security, Depends, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from i18n import t

app = FastAPI(title="Docker Backup Manager API")

# --- ZMIENNE ŚRODOWISKOWE ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
DISABLE_REGISTRATION = os.getenv("DISABLE_REGISTRATION", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)
API_KEY_SECRET = os.getenv("API_KEY")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

CONFIG_PATH = "/app/config/config.json"
RCLONE_CONFIG_PATH = "/app/config/rclone.conf"
BASE_STORAGE = "/storage"
LOGS_BASE_DIR = "/app/logs/tasks"
APP_LOG_PATH = "/app/logs/app.log"

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- UWIERZYTELNIANIE I AUTORYZACJA (JWT + BEZPIECZNY X-API-KEY) ---
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_auth(
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header)
) -> str:
    """
    Weryfikuje tożsamość na podstawie tokena JWT (Bearer) lub opcjonalnego klucza API_KEY.
    Używa stałoczasowego porównania ciągów (secrets.compare_digest), by zapobiec atakom czasowym.
    """
    if bearer and bearer.credentials:
        try:
            payload = jwt.decode(bearer.credentials, JWT_SECRET, algorithms=["HS256"])
            return payload.get("username", "authenticated_user")
        except jwt.PyJWTError:
            pass

    if api_key and API_KEY_SECRET:
        if secrets.compare_digest(api_key, API_KEY_SECRET):
            return "api_key_user"

    raise HTTPException(
        status_code=401,
        detail="Brak autoryzacji: Wymagany poprawny token JWT (Bearer) lub ważny klucz API."
    )

# --- BLOKADA I ATOMOWY ZAPIS CONFIG.JSON ---
config_lock = threading.Lock()

def save_config(data: dict):
    """
    Atomowy zapis bazy konfiguracyjnej. Zapobiega uszkodzeniu pliku przy zaniku zasilania
    oraz wyścigom wątków (Race Condition).
    """
    with config_lock:
        dir_name = os.path.dirname(CONFIG_PATH)
        os.makedirs(dir_name, exist_ok=True)
        
        # 1. Kopia bezpieczeństwa ostatniej dobrej konfiguracji
        if os.path.exists(CONFIG_PATH):
            try:
                shutil.copy2(CONFIG_PATH, CONFIG_PATH + ".bak")
            except Exception as e:
                log_to_app(f"Ostrzeżenie backupu config: {str(e)}")

        # 2. Zapis do pliku tymczasowego na tym samym systemie plików
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name

        # 3. Atomowa zamiana pliku (niepodzielna operacja na poziomie systemu)
        os.replace(temp_name, CONFIG_PATH)

def get_all_tasks() -> dict:
    with config_lock:
        if not os.path.exists(CONFIG_PATH):
            return {"tasks": []}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_to_app(f"Błąd odczytu {CONFIG_PATH}: {str(e)}")
            # Próba odczytu z kopii .bak
            bak_path = CONFIG_PATH + ".bak"
            if os.path.exists(bak_path):
                try:
                    with open(bak_path, "r", encoding="utf-8") as f_bak:
                        return json.load(f_bak)
                except Exception:
                    pass
            return {"tasks": []}

# --- SCHEDULER I ZARZĄDZANIE PROCESAMI ---
executors = {'default': ThreadPoolExecutor(max_workers=1)}
scheduler = BackgroundScheduler(executors=executors)
active_backup_processes = {}
task_progress = {}
progress_lock = threading.Lock()

def update_task_progress(task_id: int, line: str, task_type: str):
    with progress_lock:
        prog = task_progress.setdefault(task_id, {
            "task_id": task_id,
            "percent": 0,
            "speed": "",
            "transferred_files": 0,
            "total_files": None,
            "eta": "",
            "updated_at": time.time()
        })
        # 1. Procent (%)
        pct_m = re.search(r'(\d+)%', line)
        if pct_m:
            try:
                prog["percent"] = min(100, max(0, int(pct_m.group(1))))
            except Exception:
                pass

        # 2. Predkosc (np. 14.5 MB/s, 120 kB/s, 12.3MiB/s)
        spd_m = re.search(r'([\d\.]+\s*[kKMGT]?i?B/s)', line)
        if spd_m:
            prog["speed"] = spd_m.group(1).replace(" ", "")

        # 3. ETA (np. ETA 1m28s lub 0:01:23)
        eta_m = re.search(r'ETA\s+([\w\d]+)', line)
        if eta_m:
            prog["eta"] = eta_m.group(1)

        # 4. Pliki rclone (xfr# 12/350) lub rsync (xfr#12, to-chk=12/500)
        xfr_m = re.search(r'xfr#\s*(\d+)(?:/(\d+))?', line)
        if xfr_m:
            try:
                prog["transferred_files"] = int(xfr_m.group(1))
                if xfr_m.group(2):
                    prog["total_files"] = int(xfr_m.group(2))
            except Exception:
                pass

        chk_m = re.search(r'to-chk=(\d+)/(\d+)', line)
        if chk_m:
            try:
                rem, tot = int(chk_m.group(1)), int(chk_m.group(2))
                prog["total_files"] = tot
                prog["transferred_files"] = max(0, tot - rem)
            except Exception:
                pass
        prog["updated_at"] = time.time()


# --- MODELE WALIDACJI PYDANTIC ---
class LoginSchema(BaseModel):
    username: str
    password: str

class RegisterSchema(BaseModel):
    username: str
    password: str

class TaskSchema(BaseModel):
    name: str
    source: str
    destination: str
    type: Literal["local", "cloud"]
    mode: Literal["mirror", "copy", "move"]
    schedule: str
    enabled: bool = True
    restore_enabled: bool = False
    exclude: List[str] = []
    retention_days: int = 0
    discord_webhook: Optional[str] = None
    ntfy_url: Optional[str] = None
    custom_flags: Optional[List[str]] = []
    next_task_id: Optional[int] = None
    email_enabled: bool = False
    email_recipients: Optional[str] = ""
    email_level: Literal["wszystkie", "bledy_i_onedrive", "tylko_bledy"] = "wszystkie"
    last_run: Optional[str] = None

# --- POMOCNIKI LOGOWANIA I POWIADOMIEŃ ---
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
    emoji = "✅" if status in ["OK", "SUKCES", "SUCCESS"] else "❌"
    short_msg = t("notification_short", emoji=emoji, task_name=task_name, status=status)
    discord_msg = short_msg

    if skipped_files:
        discord_msg += "\n\n" + t("onedrive_path_long")
        for file_path in skipped_files[:10]:
            discord_msg += f"\n• `{file_path}`"
        if len(skipped_files) > 10:
            discord_msg += f"\n... i {len(skipped_files) - 10} więcej. Sprawdź pełny log zadania."

    # Discord
    if discord_url and discord_url not in ["string", "null", "None", ""]:
        try:
            payload = json.dumps({"content": discord_msg}).encode("utf-8")
            req = urllib.request.Request(
                discord_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "DockerBackupManager/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as e:
            log_to_app(f"Błąd powiadomienia Discord: {str(e)}")

    # Ntfy
    if ntfy_url and ntfy_url not in ["string", "null", "None", ""]:
        try:
            payload = short_msg.encode("utf-8")
            req = urllib.request.Request(
                ntfy_url,
                data=payload,
                headers={"Title": f"Backup: {task_name}", "User-Agent": "DockerBackupManager/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as e:
            log_to_app(f"Błąd powiadomienia ntfy: {str(e)}")

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
        msg["Subject"] = t("email_subject", emoji=emoji, task_name=task_name, status=status)

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        body = f"Zadanie kopii zapasowej '{task_name}' zakończyło się ze statusem: {status}.\n"
        body += f"{t('email_body_time', time=now_str)}\n\n"

        if skipped_files:
            body += f"{t('onedrive_path_long')}\n"
            for file_path in skipped_files:
                body += f"- {file_path}\n"
            body += "\n"

        error_content = ""
        if log_file_path and os.path.exists(log_file_path):
            error_lines = []
            try:
                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "ERROR" in line:
                            if "not deleting files as there were IO errors" in line or \
                               "not deleting directories as there were IO errors" in line:
                                continue
                            error_lines.append(line.strip())
            except Exception as log_err:
                body += f"[Błąd odczytu logów do załącznika: {str(log_err)}]\n"

            if error_lines:
                error_content = f"RAPORT BŁĘDÓW DLA ZADANIA: {task_name}\n"
                error_content += f"Status: {status}\nWygenerowano: {now_str}\n"
                error_content += "--------------------------------------------------\n\n"
                for err_line in error_lines:
                    error_content += f"{err_line}\n"
                body += f"🚨 Znaleziono błędy w logach ({len(error_lines)} linii ERROR). Załączono raport.\n"

        msg.attach(MIMEText(body, "plain", "utf-8"))

        if error_content:
            attachment = MIMEApplication(error_content.encode("utf-8"), _subtype="txt")
            safe_task_name = "".join(c for c in task_name if c.isalnum() or c in ("-", "_")).rstrip()
            filename = f"bledy_{safe_task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            attachment.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(attachment)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, recipients, msg.as_string())

        log_to_app(f"Powiadomienie e-mail dla zadania '{task_name}' wysłane pomyślnie.")
    except Exception as e:
        log_to_app(f"Błąd wysyłania e-maila: {str(e)}")

# --- RETENCJA KOSZA I ROTACJA ---
def clean_old_trash_folders(task: dict):
    if not isinstance(task, dict):
        return
    retention_limit = task.get("retention_days", 0)
    if retention_limit <= 0:
        return

    task_name = task.get("name") or f"Zadanie #{task.get('id', '?')}"
    task_dest = task.get("destination", "")
    task_type = task.get("type", "local")
    if not task_dest:
        return

    log_to_app(t("trash_cleaning_started", name=task_name, limit=retention_limit))
    trash_base = task_dest.rstrip("/") + "-trash"

    # Zabezpieczenie przed podaniem ścieżek krytycznych
    if not trash_base or trash_base in ["/", "/storage-trash", "/app-trash"] or (":" in trash_base and task_type == "local"):
        return

    if task["type"] == "local":
        if not os.path.exists(trash_base):
            return
        try:
            subdirs = [os.path.join(trash_base, d) for d in os.listdir(trash_base)]
            subdirs = [d for d in subdirs if os.path.isdir(d)]
            subdirs.sort()
            while len(subdirs) > retention_limit:
                oldest_folder = subdirs.pop(0)
                try:
                    shutil.rmtree(oldest_folder)
                    log_to_app(f"Retencja lokalna: Usunięto najstarszy folder kosza: {oldest_folder}")
                except Exception as rm_err:
                    log_to_app(f"Błąd retencji lokalnej przy usuwaniu {oldest_folder}: {str(rm_err)}")
        except Exception as e:
            log_to_app(f"Błąd odczytu kosza lokalnego: {str(e)}")

    elif task["type"] == "cloud":
        try:
            cmd_list = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "lsf", trash_base, "--dirs-only"]
            result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return

            subdirs = [d.strip("/") for d in result.stdout.splitlines() if d.strip()]
            subdirs.sort()
            while len(subdirs) > retention_limit:
                oldest_folder_name = subdirs.pop(0)
                full_remote_trash_path = f"{trash_base}/{oldest_folder_name}"
                cmd_purge = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "purge", full_remote_trash_path]
                result = subprocess.run(cmd_purge, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    log_to_app(f"Retencja chmury: Usunięto najstarszy folder kosza: {full_remote_trash_path}")
                else:
                    clean_error = result.stderr.strip() if result.stderr else "Nieznany błąd"
                    log_to_app(f"Błąd retencji chmury dla {full_remote_trash_path}: {clean_error}")
        except Exception as e:
            log_to_app(f"Błąd czyszczenia kosza w chmurze: {str(e)}")

def clean_all_trash_folders_cron():
    log_to_app(t("trash_cleaning_cron"))
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if task.get("enabled", True) and task.get("retention_days", 0) > 0:
            clean_old_trash_folders(task)

    log_to_app(t("logs_rotation_cron"))
    # Przed zmianą:
    # cutoff = time.time() - (365 * 24 * 60 * 60)

    # Po zmianie:
    settings = config.get("settings", {})
    # Domyślnie 365 dni, jeśli nie ustawiono w GUI
    retention_days = int(settings.get("log_retention_days", 365))
    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    if os.path.exists(LOGS_BASE_DIR):
        for root, _, files in os.walk(LOGS_BASE_DIR):
            for file in files:
                if file.endswith(".log"):
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < cutoff:
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass

# --- SILNIK WYKONYWANIA KOPII ZAPASOWYCH ---
def execute_backup_process(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        log_to_app(t("task_not_found", task_id=task_id))
        return

    # Oznaczenie statusu RUNNING
    for t_item in config.get("tasks", []):
        if t_item["id"] == task_id:
            t_item["status"] = "RUNNING"
            t_item["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    save_config(config)

    task_name_slug = "".join(c if c.isalnum() else "_" for c in task["name"]).lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")

    log_to_app(t("task_started", type=task['type'], mode=task.get('mode', 'mirror'), name=task['name']))
    cmd = []

    if task["type"] == "local":
        os.makedirs(task["destination"], exist_ok=True)
        source_path = task["source"].rstrip("/") + "/"
        cmd = ["rsync", "-rtv", "--info=progress2"]

        if task.get("mode", "mirror") == "mirror":
            cmd.append("--delete")
            if task.get("retention_days", 0) > 0:
                trash_dir = task["destination"].rstrip("/") + f"-trash/{today_str}/"
                os.makedirs(trash_dir, exist_ok=True)
                cmd.extend(["--backup", f"--backup-dir={trash_dir}"])
        elif task.get("mode") == "move":
            cmd.append("--remove-source-files")

        for ex in task.get("exclude", []):
            if ex:
                cmd.append(f"--exclude={ex}")
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

        if not any(f.startswith("--stats") for f in rclone_flags):
            cmd.extend(["--stats=1s", "--stats-one-line"])
        cmd.extend(rclone_flags)
        for ex in task.get("exclude", []):
            if ex:
                cmd.extend(["--exclude", ex])
        cmd.extend([task["source"], task["destination"], "-v"])
    else:
        return

    try:
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== START BACKUP ({task['type'].upper()}): {task['name']} ===\n")
            log_file.write(f"Komenda: {' '.join(cmd)}\n\n")
            log_file.flush()

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            active_backup_processes[task_id] = process
            with progress_lock:
                task_progress[task_id] = {
                    "task_id": task_id,
                    "percent": 0,
                    "speed": "",
                    "transferred_files": 0,
                    "total_files": None,
                    "eta": "",
                    "updated_at": time.time()
                }

            for line in iter(process.stdout.readline, ''):
                log_file.write(line)
                log_file.flush()
                update_task_progress(task_id, line, task["type"])

            process.wait()

        active_backup_processes.pop(task_id, None)
        with progress_lock:
            task_progress.pop(task_id, None)

        current_config = get_all_tasks()
        task_in_db = next((t_item for t_item in current_config.get("tasks", []) if t_item["id"] == task_id), None)
        if task_in_db and task_in_db.get("status") == "Zatrzymane":
            log_to_app(t("task_stopped_user", name=task['name']))
            return

        final_status = "OK" if process.returncode == 0 else "Błąd"
        skipped_onedrive_files = []

        # Obsługa limitu OneDrive
        if task["type"] == "cloud" and final_status == "Błąd" and os.path.exists(log_file_path):
            try:
                has_other_errors = False
                with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "ERROR :" in line:
                            if "not deleting directories as there were IO errors" in line or \
                               "not deleting files as there were IO errors" in line or \
                               "Can't retry any of the errors" in line:
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
                    log_to_app(t("onedrive_mitigated", name=task['name'], count=len(skipped_onedrive_files)))
                    final_status = "OK"
            except Exception as parse_error:
                log_to_app(f"Błąd parsowania logu OneDrive: {str(parse_error)}")

        config = get_all_tasks()
        for t_item in config.get("tasks", []):
            if t_item["id"] == task_id:
                t_item["status"] = final_status
                break
        save_config(config)

        log_to_app(t("task_finished", name=task['name'], status=final_status))

        # Powiadomienia
        try:
            send_notification(
                task["name"],
                final_status,
                discord_url=task.get("discord_webhook"),
                ntfy_url=task.get("ntfy_url"),
                skipped_files=skipped_onedrive_files if len(skipped_onedrive_files) > 0 else None
            )
        except Exception as notify_err:
            log_to_app(f"Błąd wysyłania powiadomienia: {str(notify_err)}")

        if task.get("email_enabled", False) and task.get("email_recipients"):
            email_level = task.get("email_level", "tylko_bledy")
            should_send_email = (
                email_level == "wszystkie" or
                (email_level == "bledy_i_onedrive" and (final_status == "Błąd" or len(skipped_onedrive_files) > 0)) or
                (email_level == "tylko_bledy" and final_status == "Błąd")
            )
            if should_send_email:
                send_email_notification(
                    task["name"],
                    final_status,
                    task["email_recipients"],
                    skipped_files=skipped_onedrive_files if len(skipped_onedrive_files) > 0 else None,
                    log_file_path=log_file_path
                )

        if final_status in ["OK", "SUCCESS"]:
            clean_old_trash_folders(task)
            next_id = task.get("next_task_id")
            if next_id:
                all_tasks_config = get_all_tasks()
                next_task = next((t_item for t_item in all_tasks_config.get("tasks", []) if t_item["id"] == next_id), None)
                if next_task:
                    log_to_app(t("chain_next_trigger", name=task['name'], next_id=next_id, next_name=next_task['name']))
                    scheduler.add_job(
                        execute_backup_process,
                        args=[next_task["id"]],
                        id=f"chained_{next_id}_{int(datetime.now().timestamp())}",
                        name=f"Chained Run: {next_task['name']}",
                        misfire_grace_time=None
                    )
    except Exception as e:
        config = get_all_tasks()
        for t_item in config.get("tasks", []):
            if t_item["id"] == task_id:
                t_item["status"] = "Błąd"
                break
        save_config(config)
        log_to_app(f"Krytyczny błąd {task.get('name', f'ID {task_id}')}: {str(e)}")

# --- SILNIK PRZYWRACANIA (RESTORE) ---
def execute_restore_process(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        log_to_app(t("task_not_found", task_id=task_id))
        return

    task_name_slug = "".join(c if c.isalnum() else "_" for c in task["name"]).lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_RESTORE")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")

    log_to_app(t("restore_started", name=task['name']))

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
            log_file.write(f"Komenda: {' '.join(cmd)}\n\n")
            log_file.flush()
            process = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True)

        status = "SUKCES" if process.returncode == 0 else "BŁĄD"
        log_to_app(t("restore_finished", name=task['name'], status=status))
        send_notification(f"RESTORE: {task['name']}", status, discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
    except Exception as e:
        log_to_app(f"Błąd przywracania {task['name']}: {str(e)}")

# --- HARMONOGRAM (SCHEDULER) ---
def add_task_to_scheduler(task: dict):
    if not isinstance(task, dict):
        return

    task_id = task.get("id")
    task_name = task.get("name") or f"Zadanie #{task_id or '?'}"

    if not task_id:
        log_to_app(f"Ostrzeżenie: Pominięto zadanie bez identyfikatora ID w konfiguracji.")
        return

    if not task.get("enabled", True):
        if scheduler.get_job(str(task_id)):
            scheduler.remove_job(str(task_id))
            log_to_app(f"Usunięto z harmonogramu: '{task_name}'")
        return

    schedule_expr = task.get("schedule") or task.get("cron")
    if not schedule_expr or not str(schedule_expr).strip():
        if scheduler.get_job(str(task_id)):
            scheduler.remove_job(str(task_id))
        log_to_app(f"Harmonogram dla '{task_name}': zadanie bez zdefiniowanego czasu (tylko ręczne uruchamianie).")
        return

    try:
        trigger = CronTrigger.from_crontab(str(schedule_expr).strip())
        scheduler.add_job(
            execute_backup_process, trigger=trigger, args=[task_id],
            id=str(task_id), name=task_name, replace_existing=True,
            misfire_grace_time=None
        )
        log_to_app(f"Zarejestrowano w harmonogramie: '{task_name}' ({schedule_expr})")
    except Exception as e:
        log_to_app(f"Błąd rejestracji harmonogramu dla '{task_name}' (wyrażenie cron: '{schedule_expr}'): {str(e)}")

def load_all_tasks_into_scheduler():
    config = get_all_tasks()
    tasks_list = config.get("tasks", [])
    if isinstance(tasks_list, list):
        for task in tasks_list:
            if isinstance(task, dict):
                if "mode" not in task:
                    task["mode"] = "mirror"
                try:
                    add_task_to_scheduler(task)
                except Exception as e:
                    log_to_app(f"Błąd dodawania zadania do harmonogramu: {str(e)}")
    try:
        scheduler.add_job(clean_all_trash_folders_cron, trigger=CronTrigger.from_crontab("15 0 * * *"), id="trash_cleaner", replace_existing=True)
    except Exception as e:
        log_to_app(f"Błąd rejestracji zadania czyszczenia kosza: {str(e)}")

@app.on_event("startup")
def startup_event():
    config = get_all_tasks()
    status_changed = False
    tasks_list = config.get("tasks", [])
    if isinstance(tasks_list, list):
        for task in tasks_list:
            if isinstance(task, dict):
                if task.get("status") == "RUNNING":
                    task["status"] = "Błąd"
                    task_id = task.get("id", "?")
                    task_name = task.get("name", f"ID {task_id}")
                    log_to_app(f"System: Zresetowano wiszące zadanie {task_name} ze statusu RUNNING.")
                    status_changed = True
    if status_changed:
        save_config(config)
    load_all_tasks_into_scheduler()
    scheduler.start()
    log_to_app("Harmonogram (Scheduler) i system retencji uruchomione pomyślnie.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

# --- ENDPOINTY BIZNESOWE (ZABEZPIECZONE JWT / X-API-KEY) ---
@app.get("/api/tasks", dependencies=[Depends(verify_auth)])
def get_tasks():
    data = get_all_tasks()
    with progress_lock:
        for t_item in data.get("tasks", []):
            if isinstance(t_item, dict):
                tid = t_item.get("id")
                if tid in task_progress:
                    t_item["progress"] = task_progress[tid]
    return data

@app.get("/api/tasks/progress", dependencies=[Depends(verify_auth)])
def get_all_tasks_progress():
    with progress_lock:
        return dict(task_progress)

@app.post("/api/tasks", dependencies=[Depends(verify_auth)])
def create_task(task: TaskSchema):
    config = get_all_tasks()
    existing_ids = [t_item["id"] for t_item in config.get("tasks", [])]
    new_id = max(existing_ids) + 1 if existing_ids else 1

    if task.type == "local" and not os.path.exists(task.source):
        raise HTTPException(status_code=400, detail=f"Brak katalogu źródłowego: {task.source}")

    new_task = task.dict()
    new_task["id"] = new_id
    new_task["status"] = "New"

    config.setdefault("tasks", []).append(new_task)
    save_config(config)
    add_task_to_scheduler(new_task)
    log_to_app(f"Utworzono zadanie: {task.name}")
    return {"task": new_task}

@app.put("/api/tasks/{task_id}", dependencies=[Depends(verify_auth)])
def update_task(task_id: int, fields: TaskSchema):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    idx = next((i for i, t_item in enumerate(tasks) if t_item["id"] == task_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Brak zadania")

    if fields.type == "local" and not os.path.exists(fields.source):
        raise HTTPException(status_code=400, detail=f"Brak katalogu źródłowego: {fields.source}")

    updated_task = fields.dict()
    updated_task["id"] = task_id
    updated_task["status"] = tasks[idx].get("status", "New")

    tasks[idx] = updated_task
    save_config(config)
    add_task_to_scheduler(updated_task)
    log_to_app(f"Zaktualizowano zadanie ID {task_id}: {fields.name}")
    return {"task": updated_task}

@app.delete("/api/tasks/{task_id}", dependencies=[Depends(verify_auth)])
def delete_task(task_id: int):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    if not any(t_item["id"] == task_id for t_item in tasks):
        raise HTTPException(status_code=404, detail="Brak zadania")

    config["tasks"] = [t_item for t_item in tasks if t_item["id"] != task_id]
    save_config(config)
    if scheduler.get_job(str(task_id)):
        scheduler.remove_job(str(task_id))
    log_to_app(f"Usunięto zadanie ID {task_id}.")
    return {"message": "Zadanie usunięte"}

@app.post("/api/tasks/{task_id}/run", dependencies=[Depends(verify_auth)])
def run_task(task_id: int):
    config = get_all_tasks()
    task = next((t_item for t_item in config.get("tasks", []) if t_item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Brak zadania")

    scheduler.add_job(
        execute_backup_process,
        args=[task_id],
        id=f"manual_{task_id}_{int(datetime.now().timestamp())}",
        name=f"Manual Run: {task['name']}",
        misfire_grace_time=None
    )
    log_to_app(f"Ręczne wywołanie zadania ID {task_id} przekazane do kolejki.")
    return {"message": "Zadanie przekazane do kolejki wykonawczej."}

@app.post("/api/tasks/{task_id}/stop", dependencies=[Depends(verify_auth)])
def stop_task(task_id: int):
    config = get_all_tasks()
    task = next((t_item for t_item in config.get("tasks", []) if t_item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Brak zadania")

    process = active_backup_processes.get(task_id)
    if process:
        try:
            log_to_app(f"Żądanie zatrzymania zadania ID {task_id}.")
            send_notification(task["name"], t("task_stopped_status"), discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))

            config = get_all_tasks()
            for t_item in config.get("tasks", []):
                if t_item["id"] == task_id:
                    t_item["status"] = "Zatrzymane"
                    break
            save_config(config)

            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            active_backup_processes.pop(task_id, None)
            with progress_lock:
                task_progress.pop(task_id, None)
            return {"message": "Zadanie zostało wymuszenie zatrzymane."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Błąd zatrzymywania procesu: {str(e)}")

    config = get_all_tasks()
    for t_item in config.get("tasks", []):
        if t_item["id"] == task_id and t_item["status"] == "RUNNING":
            t_item["status"] = "Zatrzymane"
            save_config(config)
            send_notification(task["name"], t("task_stopped_status"), discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
            return {"message": "Proces nie był aktywny. Zresetowano status zadania do 'Zatrzymane'."}

    raise HTTPException(status_code=400, detail="To zadanie nie jest aktualnie uruchomione.")

@app.post("/api/tasks/{task_id}/restore", dependencies=[Depends(verify_auth)])
def restore_task(task_id: int):
    config = get_all_tasks()
    task = next((t_item for t_item in config.get("tasks", []) if t_item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Brak zadania")
    if not task.get("restore_enabled", False):
        raise HTTPException(status_code=400, detail="Restore jest zablokowane w konfiguracji zadania.")

    scheduler.add_job(
        execute_restore_process,
        args=[task_id],
        id=f"manual_restore_{task_id}_{int(datetime.now().timestamp())}",
        name=f"Manual Restore: {task['name']}",
        misfire_grace_time=None
    )
    log_to_app(f"Ręczne przywracanie zadania ID {task_id} przekazane do kolejki.")
    return {"message": "Przywracanie przekazane do kolejki wykonawczej."}

@app.get("/api/tasks/{task_id}/logs", dependencies=[Depends(verify_auth)])
def get_task_logs(task_id: int):
    config = get_all_tasks()
    task = next((t_item for t_item in config.get("tasks", []) if t_item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Brak zadania")

    task_name_slug = "".join(c if c.isalnum() else "_" for c in task["name"]).lower()
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
            last_lines = lines[-250:] if len(lines) > 250 else lines
            log_content = "".join(last_lines)

        return {"filename": os.path.basename(latest_log_path), "logs": log_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu logów: {str(e)}")

# --- PRZEGLĄDANIE PLIKÓW (ZABEZPIECZONE PATH TRAVERSAL) ---
@app.get("/api/browse", dependencies=[Depends(verify_auth)])
def browse_folder(path: str = ""):
    base_storage = Path(BASE_STORAGE).resolve()
    target = (base_storage / path.lstrip("/")).resolve()

    # Ścisła weryfikacja przynależności do katalogu bazowego
    if not target.is_relative_to(base_storage) or not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Katalog nie istnieje lub dostęp zabroniony.")

    try:
        directories = [
            {"name": entry.name, "path": f"/{os.path.relpath(entry.path, str(base_storage))}"}
            for entry in os.scandir(str(target)) if entry.is_dir()
        ]
        directories.sort(key=lambda x: x["name"].lower())
        return {"current_path": path, "directories": directories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINTY AUTORYZACJI ---
@app.post("/api/auth/login")
def login(credentials: LoginSchema):
    config = get_all_tasks()
    users = config.get("users", [])
    user = next((u for u in users if u["username"] == credentials.username), None)

    # 1. Sprawdzenie konta wbudowanego administratora
    if credentials.username == ADMIN_USERNAME:
        if secrets.compare_digest(credentials.password, ADMIN_PASSWORD):
            exp = datetime.utcnow() + timedelta(days=7)
            token = jwt.encode({"username": ADMIN_USERNAME, "exp": exp}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": ADMIN_USERNAME}
        raise HTTPException(status_code=400, detail="Nieprawidłowe hasło administratora.")

    # 2. Sprawdzenie użytkownika z bazy config.json
    if user:
        password_bytes = credentials.password.encode('utf-8')
        hashed_bytes = user["password"].encode('utf-8')
        if bcrypt.checkpw(password_bytes, hashed_bytes):
            exp = datetime.utcnow() + timedelta(days=7)
            token = jwt.encode({"username": user["username"], "exp": exp}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": user["username"]}

    raise HTTPException(status_code=400, detail="Nieprawidłowy login lub hasło.")

@app.post("/api/auth/register")
def register(credentials: RegisterSchema):
    if DISABLE_REGISTRATION:
        raise HTTPException(status_code=403, detail="Rejestracja nowych kont jest zablokowana.")

    config = get_all_tasks()
    config.setdefault("users", [])

    if credentials.username == ADMIN_USERNAME or any(u["username"] == credentials.username for u in config["users"]):
        raise HTTPException(status_code=400, detail="Użytkownik o takiej nazwie już istnieje.")

    hashed_password = bcrypt.hashpw(credentials.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = {"username": credentials.username, "password": hashed_password}
    config["users"].append(new_user)
    save_config(config)

    return {"message": "Konto zarejestrowane pomyślnie."}

# --- KRYPTOGRAFICZNY EKSPORT / IMPORT (PBKDF2 + AES-GCM) ---
class CryptoHelper:
    @staticmethod
    def derive_key(password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        return kdf.derive(password.encode("utf-8"))

    @classmethod
    def encrypt_data(cls, data: bytes, password: str) -> bytes:
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = cls.derive_key(password, salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return salt + nonce + ciphertext

    @classmethod
    def decrypt_data(cls, encrypted_blob: bytes, password: str) -> bytes:
        if len(encrypted_blob) < 28:
            raise ValueError("Plik jest uszkodzony lub zbyt krótki.")
        salt = encrypted_blob[:16]
        nonce = encrypted_blob[16:28]
        ciphertext = encrypted_blob[28:]
        key = cls.derive_key(password, salt)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

@app.post("/api/config/export", dependencies=[Depends(verify_auth)])
def export_configuration(password: str = Form(...)):
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Hasło szyfrowania musi mieć co najmniej 6 znaków.")

    config_data = get_all_tasks()
    rclone_content = ""
    if os.path.exists(RCLONE_CONFIG_PATH):
        with open(RCLONE_CONFIG_PATH, "r", encoding="utf-8") as f:
            rclone_content = f.read()

    payload = {
        "version": 1,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": config_data,
        "rclone_conf": rclone_content
    }
    raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        encrypted_bytes = CryptoHelper.encrypt_data(raw_bytes, password)
        filename = f"backup_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.enc"
        return Response(
            content=encrypted_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        log_to_app(f"Błąd eksportu konfiguracji: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Błąd szyfrowania: {str(e)}")

@app.post("/api/config/import", dependencies=[Depends(verify_auth)])
async def import_configuration(password: str = Form(...), file: UploadFile = File(...)):
    if not password:
        raise HTTPException(status_code=400, detail="Brak hasła do odszyfrowania.")

    try:
        encrypted_blob = await file.read()
        decrypted_bytes = CryptoHelper.decrypt_data(encrypted_blob, password)
        payload = json.loads(decrypted_bytes.decode("utf-8"))

        if "config" not in payload:
            raise HTTPException(status_code=400, detail="Nieprawidłowa struktura konfiguracji.")

        save_config(payload["config"])
        if "rclone_conf" in payload and payload["rclone_conf"] is not None:
            os.makedirs(os.path.dirname(RCLONE_CONFIG_PATH), exist_ok=True)
            with open(RCLONE_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(payload["rclone_conf"])

        load_all_tasks_into_scheduler()
        log_to_app("Konfiguracja (config.json + rclone.conf) zaimportowana i przeładowana.")
        return {"message": "Konfiguracja zaimportowana pomyślnie."}
    except Exception as e:
        log_to_app(f"Błąd importu konfiguracji: {str(e)}")
        raise HTTPException(status_code=400, detail="Nieprawidłowe hasło lub uszkodzony plik konfiguracyjny.")

class SettingsSchema(BaseModel):
    log_retention_days: int = Field(default=365, ge=1, le=3650)

@app.get("/api/settings", dependencies=[Depends(verify_auth)])
def get_system_settings():
    config = get_all_tasks()
    settings = config.get("settings", {})
    return {
        "log_retention_days": settings.get("log_retention_days", 365),
        "rclone_flags": settings.get("rclone_flags", [])
    }

@app.post("/api/settings", dependencies=[Depends(verify_auth)])
def update_system_settings(payload: SettingsSchema):
    config = get_all_tasks()
    if "settings" not in config:
        config["settings"] = {}
    
    config["settings"]["log_retention_days"] = payload.log_retention_days
    save_config(config)
    log_to_app(f"Zaktualizowano czas retencji logów na: {payload.log_retention_days} dni")
    return {"status": "success", "settings": config["settings"]}