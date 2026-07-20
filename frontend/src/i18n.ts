import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  pl: {
    translation: {
      // Login & Register
      "login_title": "Wprowadź poświadczenia, aby zarządzać kopiami",
      "register_title": "Utwórz nowe konto użytkownika systemowego",
      "user_label": "Użytkownik",
      "pass_label": "Hasło dostępu",
      "confirm_pass_label": "Powtórz hasło",
      "btn_login": "Zaloguj się",
      "btn_register": "Zarejestruj nowe konto",
      "toggle_to_register": "Nie masz jeszcze konta? Zarejestruj się",
      "toggle_to_login": "Masz już konto? Wróć do logowania",
      "loading_text": "Przetwarzanie...",
      "confirm_pass_error": "Podane hasła nie są identyczne.",
      "register_success_msg": "Konto utworzone pomyślnie! Możesz się teraz zalogować.",
      
      // Dashboard Header & Navigation
      "logged_in_as": "Zalogowany jako",
      "btn_logout": "Wyloguj się",
      "dashboard_title": "Zadania automatyczne",
      "btn_refresh": "Odśwież",
      "btn_new_task": "Nowe zadanie",
      "no_tasks": "Brak zdefiniowanych zadań backupu.",
      
      // Task Cards Labels & Statuses
      "lbl_source": "Źródło",
      "lbl_destination": "Cel",
      "lbl_mode": "Tryb",
      "lbl_run": "Uruchom",
      "task_paused": "Wstrzymane",
      "status_success": "Sukces",
      "status_error": "Błąd",
      "status_never": "Nieuruchamiane",
      
      // Modals & Alerts General
      "task_queued_alert": "Zadanie przekazane do kolejki NAS (wykonywanie jedno po drugim).",
      "restore_queued_alert": "Procedura Restore została pomyślnie dodana do kolejki!",
      "delete_confirm_msg": "Czy na pewno chcesz bezpowrotnie usunąć zadanie: \"{{name}}\"?",
      "restore_confirm_msg": "⚠️ UWAGA! Rozpoczynasz procedurę przywracania danych dla zadania: \"{{name}}\".\n\nCzy na pewno chcesz kontynuować?",
      "restore_disabled_alert": "Operacja zablokowana. Włącz opcję \"Zezwól na operacje Restore\" w edycji zadania \"{{name}}\".",
      "btn_cancel": "Anuluj",
      "btn_save_changes": "Zapisz zmiany",
      "saving_text": "Zapisywanie...",
      "error_fetch_logs": "Błąd pobierania logów",
	  "stop_confirm_msg": "Czy na pewno chcesz wymusić natychmiastowe zatrzymanie tego zadania?", // <-- DODAJ TĘ LINIĘ

      // TaskModal Specific
      "modal_edit_title": "Edycja Zadania Backup",
      "modal_create_title": "Nowe Zadanie Kopiowania",
      "lbl_copy_type": "Typ Kopii",
      "lbl_local_rsync": "Lokalna (Rsync)",
      "lbl_cloud_rclone": "Chmura (Rclone)",
      "lbl_task_name": "Nazwa Zadania",
      "ph_task_name": "np. Kopia Dokumentów Domowych",
      "lbl_src_dir": "Katalog Źródłowy",
      "ph_src_dir": "np. /storage/dokumenty",
      "btn_browse": "Przeglądaj",
      "lbl_dest_dir": "Katalog Celu / Zdalny Zasób",
      "lbl_sync_mode": "Tryb synchronizacji",
      "mode_mirror": "Mirror (Sync / Lustro)",
      "mode_copy": "Copy (Tylko Kopiuj nowe)",
      "mode_move": "Move (Przenieś i skasuj źródło)",
      "lbl_cron": "Harmonogram (Cron)",
      "ph_cron": "np. 0 3 * * *",
      "lbl_retention": "Retencja Kosza (wersje)",
      "lbl_exclusions": "Wykluczenia plików (rozdziel przecinkami)",
      "lbl_rclone_flags": "Custom Rclone Flags (rozdziel przecinkami)",
      "ph_exclusions": "np. .DS_Store, *.tmp",
      "lbl_cron_active": "Zadanie aktywne (Harmonogram)",
      "lbl_allow_restore": "Zezwól na operacje Restore",

      // FolderBrowserModal Specific
      "browser_src_title": "Wybierz katalog źródłowy na NAS",
      "browser_dest_title": "Wybierz katalog docelowy na NAS",
      "browser_loading": "Odpytywanie dysków NAS...",
      "browser_empty": "Ten folder jest pusty lub nie zawiera podkatalogów.",
      "browser_go_up": ".. (W górę)",
      "btn_select_folder": "Wybierz ten folder",
      "error_folder_format": "Serwer zwrócił nieznany format danych.",
      "error_folder_fetch": "Nie udało się wczytać zawartości folderu.",

      // LogModal Specific
      "log_title": "Logi wykonania:",
      "log_loading": "Pobieranie logów z serwera NAS...",
      "log_empty": "Brak zawartości w pliku logu.",
      "tooltip_refresh_logs": "Odśwież logi",
	  
	  "tooltip_logs": "Zobacz najnowsze logi",
	  "tooltip_edit": "Edytuj zadanie",
	  "tooltip_delete": "Usuń zadanie",
	  "status_processing": "W trakcie...",
	  "lbl_next_task": "Następne zadanie w łańcuchu (potok)",
      "option_none": "--- Brak (koniec łańcucha) ---",
	  "cloned_suffix": "Kopia",
	  "tooltip_clone": "Klonuj zadanie", // <-- DODAJ TĘ LINIĘ
	  "sec_email_settings": "Powiadomienia E-mail (Gmail)",
	  "lbl_email_active": "Włącz powiadomienia e-mail dla tego zadania",
	  "lbl_email_recipients": "Adresy odbiorców (rozdzielane przecinkami)",
	  "lbl_email_level": "Warunek wysyłki",
	  "email_lvl_all": "Wszystkie (Zawsze wysyłaj)",
	  "email_lvl_warnings": "Błędy oraz ostrzeżenia ścieżek",
	  "email_lvl_errors": "Tylko krytyczne błędy",
	  "lbl_last_run": "Ostatnie uruchomienie"
    }
  },
  en: {
    translation: {
      // Login & Register
      "login_title": "Enter credentials to manage backups",
      "register_title": "Create a new system user account",
      "user_label": "Username",
      "pass_label": "Password",
      "confirm_pass_label": "Confirm Password",
      "btn_login": "Sign In",
      "btn_register": "Register New Account",
      "toggle_to_register": "Don't have an account? Sign up",
      "toggle_to_login": "Already have an account? Go back",
      "loading_text": "Processing...",
      "confirm_pass_error": "Passwords do not match.",
      "register_success_msg": "Account created successfully! You can now log in.",
      
      // Dashboard Header & Navigation
      "logged_in_as": "Logged in as",
      "btn_logout": "Log Out",
      "dashboard_title": "Automated Tasks",
      "btn_refresh": "Refresh",
      "btn_new_task": "New Task",
      "no_tasks": "No backup tasks defined.",
      
      // Task Cards Labels & Statuses
      "lbl_source": "Source",
      "lbl_destination": "Destination",
      "lbl_mode": "Mode",
      "lbl_run": "Run",
      "task_paused": "Paused",
      "status_success": "Success",
      "status_error": "Error",
      "status_never": "Never Executed",
      
      // Modals & Alerts General
      "task_queued_alert": "Task sent to NAS queue (sequential execution active).",
      "restore_queued_alert": "Restore procedure successfully added to the queue!",
      "delete_confirm_msg": "Are you sure you want to permanently delete task: \"{{name}}\"?",
      "restore_confirm_msg": "⚠️ WARNING! You are starting data restoration process for task: \"{{name}}\".\n\nDo you really want to continue?",
      "restore_disabled_alert": "Operation blocked. Enable \"Allow Restore operations\" in the settings for task \"{{name}}\".",
      "btn_cancel": "Cancel",
      "btn_save_changes": "Save Changes",
      "saving_text": "Saving...",
      "error_fetch_logs": "Error retrieving logs",
	  "stop_confirm_msg": "Are you sure you want to forcefully terminate this running task?", // <-- DODAJ TĘ LINIĘ

      // TaskModal Specific
      "modal_edit_title": "Edit Backup Task",
      "modal_create_title": "New Copy Task",
      "lbl_copy_type": "Copy Type",
      "lbl_local_rsync": "Local (Rsync)",
      "lbl_cloud_rclone": "Cloud (Rclone)",
      "lbl_task_name": "Task Name",
      "ph_task_name": "e.g., Home Documents Backup",
      "lbl_src_dir": "Source Directory",
      "ph_src_dir": "e.g., /storage/documents",
      "btn_browse": "Browse",
      "lbl_dest_dir": "Destination Directory / Remote Resource",
      "lbl_sync_mode": "Synchronization Mode",
      "mode_mirror": "Mirror (Sync)",
      "mode_copy": "Copy (New files only)",
      "mode_move": "Move (Transfer & erase source)",
      "lbl_cron": "Schedule (Cron)",
      "ph_cron": "e.g., 0 3 * * *",
      "lbl_retention": "Trash Retention (versions)",
      "lbl_exclusions": "File Exclusions (comma-separated)",
      "lbl_rclone_flags": "Custom Rclone Flags (comma-separated)",
      "ph_exclusions": "e.g., .DS_Store, *.tmp",
      "lbl_cron_active": "Task Active (Schedule)",
      "lbl_allow_restore": "Allow Restore Operations",

      // FolderBrowserModal Specific
      "browser_src_title": "Select source directory on NAS",
      "browser_dest_title": "Select destination directory on NAS",
      "browser_loading": "Querying NAS drives...",
      "browser_empty": "This folder is empty or contains no subdirectories.",
      "browser_go_up": ".. (Go Up)",
      "btn_select_folder": "Select this folder",
      "error_folder_format": "Server returned an unknown data format.",
      "error_folder_fetch": "Failed to load folder contents.",

      // LogModal Specific
      "log_title": "Execution logs:",
      "log_loading": "Retrieving logs from NAS server...",
      "log_empty": "No contents found in the log file.",
      "tooltip_refresh_logs": "Refresh logs",
	  
	  "tooltip_logs": "View latest logs",
	  "tooltip_edit": "Edit task",
	  "tooltip_delete": "Delete task",
	  "status_processing": "Processing...",
	  "lbl_next_task": "Next task in chain (pipeline)",
      "option_none": "--- None (end of chain) ---",
	  "cloned_suffix": "Copy",
	  "tooltip_clone": "Clone task", // <-- DODAJ TĘ LINIĘ
	  "sec_email_settings": "E-mail notifications (Gmail)",
	  "lbl_email_active": "Enable email notifications for this task.",
	  "lbl_email_recipients": "Recipient addresses (comma-separated)",
	  "lbl_email_level": "Shipping condition",
	  "email_lvl_all": "All (Always send)",
	  "email_lvl_warnings": "Path errors and warnings",
	  "email_lvl_errors": "Critical errors only",
	  "lbl_last_run": "Last run"
    }
  }
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: localStorage.getItem('backup_lang') || 'pl',
    fallbackLng: 'pl',
    interpolation: {
      escapeValue: false
    }
  });

export default i18n;