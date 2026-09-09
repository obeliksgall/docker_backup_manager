import os

APP_LANG = os.getenv("APP_LANG", "pl").lower()

MESSAGES = {
    "pl": {
        "task_started": "Uruchamianie zadania ({type} - {mode}): {name}.",
        "task_finished": "Zadanie {name} zakończone statusem: {status}.",
        "task_stopped_user": "Zadanie '{name}' zostało przerwane na żądanie użytkownika.",
        "task_stopped_status": "Zatrzymane na żądanie 🛑",
        "task_not_found": "Błąd: Zadanie o ID {task_id} nie istnieje w bazie config.json.",
        "notification_short": "{emoji} Zadanie '{task_name}' zakończyło się statusem: {status}.",
        "onedrive_path_long": "⚠️ Wykryto zbyt długie ścieżki (Pominięte przez OneDrive - limit 400 znaków):",
        "onedrive_mitigated": "Zadanie '{name}': Wykryto {count} błędów typu 'pathIsTooLong'. Status złagodzony do 'OK'.",
        "email_subject": "{emoji} Backup: {task_name} - Status: {status}",
        "email_body_time": "Czas raportu: {time}",
        "trash_cleaning_started": "Uruchomiono czyszczenie kosza dla zadania '{name}' (Limit wersji: {limit}).",
        "trash_cleaning_cron": "Harmonogram: Uruchomiono nocne czyszczenie kosza dla wszystkich zadań.",
        "logs_rotation_cron": "Harmonogram: Uruchomiono czyszczenie logów starszych niż 365 dni.",
        "restore_started": "Uruchamianie PRZYWRACANIA dla zadania: {name}.",
        "restore_finished": "Przywracanie {name} zakończone: {status}.",
        "chain_next_trigger": "Łańcuch zadań: Zadanie '{name}' zakończone sukcesem. Wywoływanie zadania ID {next_id}: '{next_name}'."
    },
    "en": {
        "task_started": "Starting task ({type} - {mode}): {name}.",
        "task_finished": "Task {name} finished with status: {status}.",
        "task_stopped_user": "Task '{name}' was stopped by user request.",
        "task_stopped_status": "Stopped on request 🛑",
        "task_not_found": "Error: Task ID {task_id} does not exist in config.json.",
        "notification_short": "{emoji} Task '{task_name}' finished with status: {status}.",
        "onedrive_path_long": "⚠️ Path too long detected (Skipped by OneDrive - 400 chars limit):",
        "onedrive_mitigated": "Task '{name}': Detected {count} 'pathIsTooLong' errors. Status mitigated to 'OK'.",
        "email_subject": "{emoji} Backup: {task_name} - Status: {status}",
        "email_body_time": "Report time: {time}",
        "trash_cleaning_started": "Started trash cleanup for task '{name}' (Retention limit: {limit}).",
        "trash_cleaning_cron": "Schedule: Nightly trash cleanup started for all tasks.",
        "logs_rotation_cron": "Schedule: Log rotation started for logs older than 365 days.",
        "restore_started": "Starting RESTORE for task: {name}.",
        "restore_finished": "Restore {name} finished: {status}.",
        "chain_next_trigger": "Task chain: Task '{name}' succeeded. Triggering next task ID {next_id}: '{next_name}'."
    }
}

def t(key: str, **kwargs) -> str:
    lang_dict = MESSAGES.get(APP_LANG, MESSAGES["pl"])
    template = lang_dict.get(key, MESSAGES["pl"].get(key, key))
    return template.format(**kwargs) if kwargs else template
