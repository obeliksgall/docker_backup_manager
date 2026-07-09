import os
import json
import subprocess
import urllib.request

import bcrypt
import jwt

import time                                 # <-- REQUIRED for time.time()
import logging                              # <-- REQUIRED for logging
from logging.handlers import RotatingFileHandler  # <-- REQUIRED for log rotation

from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends
from pydantic import BaseModel
from typing import Optional, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
# THREAD POOL EXECUTOR IMPORT FOR TASK QUEUING
from apscheduler.executors.pool import ThreadPoolExecutor

from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Docker Backup Manager API")

# Fetch environment variables from .env
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
    allow_origins=["*"],  # Allow traffic from local network devices
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
            detail="Access Denied: Invalid or missing API key (X-API-Key)."
        )
    return api_key

# --- TASK QUEUING CONFIGURATION FOR NAS ---
executors = {
    'default': ThreadPoolExecutor(max_workers=1)
}
scheduler = BackgroundScheduler(executors=executors)

# Stores references to active system processes {task_id: subprocess.Popen}
active_backup_processes = {}

# --- DATA VALIDATION SCHEMA ---
class TaskSchema(BaseModel):
    name: str
    source: str
    destination: str
    type: str                  # "local" or "cloud"
    mode: str                  # "mirror", "incremental", "move"
    schedule: str              # Cron expression, e.g., "0 3 * * *"
    enabled: bool = True       # Active in scheduler
    restore_enabled: bool = False # Safety switch for Restore
    exclude: List[str] = []    # Ignored files/folders
    retention_days: int = 0    # Number of trash versions to keep (0 = disabled)
    discord_webhook: Optional[str] = None
    ntfy_url: Optional[str] = None
    custom_flags: Optional[List[str]] = []  # <-- CUSTOM RCLONE FLAGS PER TASK

# --- HELPER FUNCTIONS ---
def log_to_app(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(APP_LOG_PATH), exist_ok=True)
    
    logger = logging.getLogger("AppLogger")
    
    if not logger.handlers:
        handler = RotatingFileHandler(APP_LOG_PATH, maxBytes=5*1024*1024, backupCount=7, encoding="utf-8")
        formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    logger.info(message)

def send_notification(task_name: str, status: str, discord_url: str = None, ntfy_url: str = None):
    emoji = "✅" if status in ["OK", "SUKCES", "SUCCESS"] else "❌"
    msg = f"{emoji} Task '{task_name}' finished with status: {status}."
    
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
        except Exception as e: log_to_app(f"Discord notification error: {str(e)}")

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
        except Exception as e: log_to_app(f"Ntfy notification error: {str(e)}")

def save_config(data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_all_tasks():
    if not os.path.exists(CONFIG_PATH):
        return {"tasks": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# --- AUTOMATIC TRASH CLEANING (VERSION RETENTION) ---
def clean_old_trash_folders(task: dict):
    retention_limit = task.get("retention_days", 0)
    if retention_limit <= 0:
        return

    log_to_app(f"Trash cleanup triggered for task '{task['name']}' (Retention limit: {retention_limit}).")

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
                log_to_app(f"Local Retention: Removed oldest trash folder: {oldest_folder}")
        except Exception as e:
            log_to_app(f"Local trash cleanup error: {str(e)}")

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
                log_to_app(f"Cloud Retention: Removed oldest trash folder: {full_remote_trash_path}")
        except Exception as e:
            log_to_app(f"Cloud trash cleanup error: {str(e)}")

def clean_all_trash_folders_cron():
    log_to_app("Scheduler: Started nightly trash retention process for all tasks.")
    config = get_all_tasks()
    for task in config.get("tasks", []):
        if task.get("enabled", True) and task.get("retention_days", 0) > 0:
            clean_old_trash_folders(task)
            
    # --- LOG ROTATION SECTOR (OLDER THAN 365 DAYS) ---
    log_to_app("Scheduler: Started log cleanup for files older than 365 days.")
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
def execute_backup_process(task: dict):
    config = get_all_tasks()
    for t in config.get("tasks", []):
        if t["id"] == task["id"]:
            t["status"] = "RUNNING"
            break
    save_config(config)

    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")
    
    log_to_app(f"Starting task ({task['type']} - {task.get('mode', 'mirror')}): {task['name']}.")
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
            
        # --- DYNAMIC FLAG INJECTION (TASK -> GLOBAL -> FALLBACK) ---
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
            active_backup_processes[task["id"]] = process
            process.wait()
            
        active_backup_processes.pop(task["id"], None)
        final_status = "SUCCESS" if process.returncode == 0 else "ERROR"
        
        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task["id"]:
                t["status"] = final_status
                break
        save_config(config)
        
        log_to_app(f"Task '{task['name']}' finished with status: {final_status}.")
        send_notification(task["name"], final_status, discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
        
        if final_status == "SUCCESS":
            clean_old_trash_folders(task)
    except Exception as e:
        config = get_all_tasks()
        for t in config.get("tasks", []):
            if t["id"] == task["id"]:
                t["status"] = "ERROR"
                break
        save_config(config)
        log_to_app(f"Critical error in task '{task['name']}': {str(e)}")

# --- RESTORE ENGINE ---
def execute_restore_process(task: dict):
    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    os.makedirs(task_log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_RESTORE")
    log_file_path = os.path.join(task_log_dir, f"{timestamp}.log")
    
    log_to_app(f"Starting DATA RESTORE procedure for task: {task['name']}.")
    
    if task["type"] == "local":
        os.makedirs(task["source"], exist_ok=True)
        dest_path = task["destination"].rstrip("/") + "/"
        cmd = ["rsync", "-rtv", dest_path, task["source"]]
    elif task["type"] == "cloud":
        cmd = ["rclone", f"--config={RCLONE_CONFIG_PATH}", "copy", task["destination"], task["source"], "-v"]
        
        # --- INJECT DYNAMIC OPTIMIZATION FLAGS TO RESTORE ENGINE ---
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
            
        status = "SUCCESS" if process.returncode == 0 else "ERROR"
        log_to_app(f"Restore procedure for '{task['name']}' finished: {status}.")
        send_notification(f"RESTORE: {task['name']}", status, discord_url=task.get("discord_webhook"), ntfy_url=task.get("ntfy_url"))
    except Exception as e:
        log_to_app(f"Restore system error for '{task['name']}': {str(e)}")

# --- SCHEDULER ENGINE ---
def add_task_to_scheduler(task: dict):
    if not task.get("enabled", True):
        if scheduler.get_job(str(task["id"])):
            scheduler.remove_job(str(task["id"]))
            log_to_app(f"Removed from scheduler (disabled): '{task['name']}'")
        return
    try:
        trigger = CronTrigger.from_crontab(task["schedule"])
        scheduler.add_job(
            execute_backup_process, trigger=trigger, args=[task],
            id=str(task["id"]), name=task["name"], replace_existing=True
        )
        log_to_app(f"Registered in scheduler: '{task['name']}' ({task['schedule']})")
    except Exception as e:
        log_to_app(f"Scheduler registration failed for '{task['name']}': {str(e)}")

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
    log_to_app("Scheduler engine and trash retention services started successfully (Queue system operational).")

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
        raise HTTPException(status_code=400, detail=f"Source directory not found: {task.source}")
    elif task.type == "cloud" and not os.path.exists(task.destination) and not task.destination.startswith("http"):
        os.makedirs(task.destination, exist_ok=True)
        
    new_task = task.dict()
    new_task["id"] = new_id
    new_task["status"] = "New"
    
    config.setdefault("tasks", []).append(new_task)
    save_config(config)
    add_task_to_scheduler(new_task)
    log_to_app(f"Created backup task: {task.name}")
    return {"task": new_task}

@app.put("/api/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
def update_task(task_id: int, fields: TaskSchema):
    config = get_all_tasks()
    tasks = config.get("tasks", [])
    idx = next((i for i, t in enumerate(tasks) if t["id"] == task_id), None)
    
    if idx is None: raise HTTPException(status_code=404, detail="Task not found")
    
    if fields.type == "local" and not os.path.exists(fields.source):
        raise HTTPException(status_code=400, detail="Source directory not found")
    elif fields.type == "cloud" and not os.path.exists(fields.destination):
        os.makedirs(fields.destination, exist_ok=True)
    
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
    return {"message": "Task deleted successfully"}

@app.post("/api/tasks/{task_id}/run", dependencies=[Depends(verify_api_key)])
def run_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    
    scheduler.add_job(
        execute_backup_process, 
        args=[task], 
        id=f"manual_{task_id}_{int(datetime.now().timestamp())}", 
        name=f"Manual Run: {task['name']}"
    )
    log_to_app(f"Manual invocation for task ID {task_id} added to the execution thread pool.")
    return {"message": "Task forwarded to execution queue (processing tasks sequentially)."}

@app.post("/api/tasks/{task_id}/stop", dependencies=[Depends(verify_api_key)])
def stop_task(task_id: int):
    process = active_backup_processes.get(task_id)
    
    if process:
        try:
            log_to_app(f"Stop requested for task ID {task_id}. Transmitting termination signals.")
            process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                
            return {"message": "Task process terminated forcefully."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to kill running subprocess: {str(e)}")
            
    config = get_all_tasks()
    for t in config.get("tasks", []):
        if t["id"] == task_id and t["status"] == "RUNNING":
            t["status"] = "ERROR"
            save_config(config)
            log_to_app(f"Manually cleared hanging RUNNING status for task ID {task_id}.")
            return {"message": "Process wasn't active. Task status reset to 'ERROR'."}
            
    raise HTTPException(status_code=400, detail="This task is not currently active.")

@app.post("/api/tasks/{task_id}/restore", dependencies=[Depends(verify_api_key)])
def restore_task(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    if not task.get("restore_enabled", False):
        raise HTTPException(status_code=400, detail="Data restore is locked in task configuration.")
        
    scheduler.add_job(
        execute_restore_process, 
        args=[task], 
        id=f"manual_restore_{task_id}_{int(datetime.now().timestamp())}", 
        name=f"Manual Restore: {task['name']}"
    )
    log_to_app(f"Manual restore request for task ID {task_id} dispatched to thread pool.")
    return {"message": "Restore procedure submitted to execution queue."}

@app.get("/api/tasks/{task_id}/logs", dependencies=[Depends(verify_api_key)])
def get_task_logs(task_id: int):
    config = get_all_tasks()
    task = next((t for t in config.get("tasks", []) if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task_name_slug = task["name"].replace(" ", "_").lower()
    task_log_dir = os.path.join(LOGS_BASE_DIR, task_name_slug)
    
    if not os.path.exists(task_log_dir):
        return {"logs": "No logs recorded for this task. It hasn't been executed yet."}
        
    try:
        log_files = [os.path.join(task_log_dir, f) for f in os.listdir(task_log_dir) if f.endswith(".log")]
        if not log_files:
            return {"logs": "Log directory is empty."}
            
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
        raise HTTPException(status_code=500, detail=f"Log compilation error: {str(e)}")

@app.get("/api/browse", dependencies=[Depends(verify_api_key)])
def browse_folder(path: str = ""):
    full_path = os.path.normpath(os.path.join(BASE_STORAGE, path.lstrip("/")))
    if not full_path.startswith(BASE_STORAGE) or not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Directory path not found")
    try:
        directories = [{"name": entry.name, "path": f"/{os.path.relpath(entry.path, BASE_STORAGE)}"} 
                       for entry in os.scandir(full_path) if entry.is_dir()]
        directories.sort(key=lambda x: x["name"].lower())
        return {"current_path": path, "directories": directories}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    
# --- AUTHENTICATION AND REGISTRATION SECTOR ---

@app.post("/api/auth/login")
def login(credentials: LoginSchema):
    config = get_all_tasks()
    users = config.get("users", [])
    
    user = next((u for u in users if u["username"] == credentials.username), None)
    
    if not user and credentials.username == ADMIN_USERNAME:
        if credentials.password == ADMIN_PASSWORD:
            token = jwt.encode({"username": ADMIN_USERNAME}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": ADMIN_USERNAME}
        raise HTTPException(status_code=400, detail="Invalid administrator credentials.")
        
    if user:
        password_bytes = credentials.password.encode('utf-8')
        hashed_bytes = user["password"].encode('utf-8')
        if bcrypt.checkpw(password_bytes, hashed_bytes):
            token = jwt.encode({"username": user["username"]}, JWT_SECRET, algorithm="HS256")
            return {"token": token, "username": user["username"]}
            
    raise HTTPException(status_code=400, detail="Invalid username or password.")

@app.post("/api/auth/register")
def register(credentials: RegisterSchema):
    if DISABLE_REGISTRATION:
        raise HTTPException(status_code=403, detail="New account registrations are blocked by the administrator.")
        
    config = get_all_tasks()
    config.setdefault("users", [])
    
    if any(u["username"] == credentials.username for u in config["users"]):
        raise HTTPException(status_code=400, detail="A user with this name already exists.")
        
    hashed_password = bcrypt.hashpw(credentials.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = {
        "username": credentials.username,
        "password": hashed_password
    }
    config["users"].append(new_user)
    save_config(config)
    
    return {"message": "Account registered successfully."}