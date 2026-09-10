import React, { useState, useEffect } from 'react';
import { useTranslation, Trans } from 'react-i18next';
import { 
  X, 
  Download, 
  Upload, 
  Lock, 
  ShieldCheck, 
  AlertCircle, 
  Settings, 
  Clock, 
  Save,
  FileCode
} from 'lucide-react';

interface ConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportSuccess: () => void;
  apiUrl: string;
  getHeaders: () => Record<string, string>;
}

export default function ConfigModal({ isOpen, onClose, onImportSuccess, apiUrl, getHeaders }: ConfigModalProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'settings' | 'export' | 'import'>('settings');
  
  // Eksport i import
  const [exportPassword, setExportPassword] = useState('');
  const [importPassword, setImportPassword] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);

  // Ustawienia retencji logów
  const [logRetentionDays, setLogRetentionDays] = useState<number>(365);
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  // Komunikaty stanu
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Pobieranie aktualnych ustawień z backendu przy otwarciu okna
  useEffect(() => {
    if (!isOpen) return;

    const fetchSettings = async () => {
      setLoadingSettings(true);
      try {
        const res = await fetch(`${apiUrl}/api/settings`, {
          credentials: 'include',
          headers: getHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          if (data.log_retention_days !== undefined) {
            setLogRetentionDays(Number(data.log_retention_days));
          }
        }
      } catch (err) {
        console.error('Błąd pobierania ustawień:', err);
      } finally {
        setLoadingSettings(false);
      }
    };

    fetchSettings();
  }, [isOpen, apiUrl]);

  if (!isOpen) return null;

  // Zapisywanie ustawień retencji
  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingSettings(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const headers = getHeaders();
      headers['Content-Type'] = 'application/json';

      const res = await fetch(`${apiUrl}/api/settings`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ log_retention_days: Number(logRetentionDays) })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || t('err_save_settings') || 'Błąd zapisu ustawień retencji.');
      }

      setSuccessMsg(t('msg_save_settings_success', { days: logRetentionDays }) || `Zaktualizowano retencję na ${logRetentionDays} dni.`);
    } catch (err: any) {
      setError(err.message || 'Wystąpił nieoczekiwany błąd.');
    } finally {
      setSavingSettings(false);
    }
  };

  // Obsługa eksportu
  const handleExport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!exportPassword) return;

    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const formData = new FormData();
      formData.append('password', exportPassword);

      const headers = getHeaders();
      delete headers['Content-Type'];

      const res = await fetch(`${apiUrl}/api/config/export`, {
        method: 'POST',
        headers: headers,
        body: formData
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Błąd generowania pliku eksportu');
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `backup_config_${new Date().toISOString().slice(0, 10)}.enc`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setSuccessMsg(t('msg_export_success') || 'Pomyślnie pobrano zaszyfrowany plik konfiguracji.');
      setExportPassword('');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Obsługa importu
  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importPassword || !importFile) return;

    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const formData = new FormData();
      formData.append('password', importPassword);
      formData.append('file', importFile);

      const headers = getHeaders();
      delete headers['Content-Type'];

      const res = await fetch(`${apiUrl}/api/config/import`, {
        method: 'POST',
        headers: headers,
        body: formData
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Błąd importu konfiguracji');
      }

      setSuccessMsg(t('msg_import_success') || 'Konfiguracja została odszyfrowana i wczytana!');
      setImportPassword('');
      setImportFile(null);
      setTimeout(() => {
        onImportSuccess();
        onClose();
      }, 1500);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-md rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        
        {/* NAGŁÓWEK */}
        <div className="flex justify-between items-center p-5 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-bold text-white">
              {t('modal_config_title') || 'Zarządzanie Konfiguracją'}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* ZAKŁADKI: USTAWIENIA / EKSPORT / IMPORT */}
        <div className="flex border-b border-slate-800 bg-slate-950/40 p-1">
          <button
            onClick={() => { setActiveTab('settings'); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-xl transition flex items-center justify-center gap-1.5 cursor-pointer ${
              activeTab === 'settings' ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Settings className="w-3.5 h-3.5" /> {t('tab_settings') || 'Ustawienia'}
          </button>
          <button
            onClick={() => { setActiveTab('export'); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-xl transition flex items-center justify-center gap-1.5 cursor-pointer ${
              activeTab === 'export' ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Download className="w-3.5 h-3.5" /> {t('tab_export') || 'Eksport (Kopia)'}
          </button>
          <button
            onClick={() => { setActiveTab('import'); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-xl transition flex items-center justify-center gap-1.5 cursor-pointer ${
              activeTab === 'import' ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Upload className="w-3.5 h-3.5" /> {t('tab_import') || 'Import (Przywróć)'}
          </button>
        </div>

        <div className="p-6 space-y-4 text-sm text-slate-300">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-xl flex items-center gap-2 text-xs">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {successMsg && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-3 rounded-xl flex items-center gap-2 text-xs">
              <ShieldCheck className="w-4 h-4 flex-shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* ZAKŁADKA 1: USTAWIENIA RETENCJI LOGÓW */}
          {activeTab === 'settings' && (
            <form onSubmit={handleSaveSettings} className="space-y-4">
              <div>
                <div className="flex items-center gap-1.5 text-slate-200 font-medium mb-1 text-xs">
                  <Clock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{t('lbl_retention_days') || 'Czas retencji plików logów (dni)'}</span>
                </div>
                <p className="text-[11px] text-slate-400 mb-3 leading-relaxed">
                  {t('desc_retention_days') || 'Określa, po ilu dniach stare pliki logów zadań z katalogu logs/ są automatycznie usuwane podczas nocnej rotacji.'}
                </p>

                {/* Szybkie przyciski wyboru dni */}
                <div className="grid grid-cols-5 gap-1.5 mb-2.5">
                  {[7, 14, 30, 90, 365].map((days) => (
                    <button
                      key={days}
                      type="button"
                      onClick={() => setLogRetentionDays(days)}
                      className={`py-1.5 text-xs rounded-lg border font-medium transition cursor-pointer ${
                        logRetentionDays === days
                          ? 'bg-indigo-600 border-indigo-500 text-white shadow-sm'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      {days} {t('days_unit') || 'dni'}
                    </button>
                  ))}
                </div>

                <div className="relative">
                  <input
                    type="number"
                    min={1}
                    max={3650}
                    required
                    disabled={loadingSettings}
                    value={logRetentionDays}
                    onChange={(e) => setLogRetentionDays(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
                    placeholder="30"
                  />
                  <span className="absolute right-3 top-2 text-xs text-slate-500">{t('days_unit') || 'dni'}</span>
                </div>
              </div>

              <button
                type="submit"
                disabled={savingSettings || loadingSettings}
                className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium text-xs rounded-xl flex items-center justify-center gap-2 transition shadow-md cursor-pointer"
              >
                <Save className="w-4 h-4" /> 
                {savingSettings ? t('saving_text') : (t('btn_save_settings') || 'Zapisz ustawienia retencji')}
              </button>
            </form>
          )}

          {/* ZAKŁADKA 2: EKSPORT KONFIGURACJI */}
          {activeTab === 'export' && (
            <form onSubmit={handleExport} className="space-y-4">
              <p className="text-xs text-slate-400 leading-relaxed">
                <Trans i18nKey="desc_export">
                  Pobierz zaszyfrowaną kopię zapasową pliku <code className="text-indigo-400">config.json</code> oraz ustawień połączeń <code className="text-indigo-400">rclone.conf</code>.
                </Trans>
              </p>
              <div>
                <label className="block text-slate-400 font-medium mb-1.5 text-xs">
                  {t('lbl_export_password') || 'Hasło do zaszyfrowania pliku'}
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
                  <input
                    required
                    type="password"
                    value={exportPassword}
                    onChange={(e) => setExportPassword(e.target.value)}
                    placeholder={t('ph_export_password') || 'Wpisz bezpieczne hasło...'}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={loading || !exportPassword}
                className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium text-xs rounded-xl flex items-center justify-center gap-2 transition shadow-md cursor-pointer"
              >
                <Download className="w-4 h-4" /> {loading ? t('saving_text') : (t('btn_download_export') || 'Pobierz zaszyfrowany plik')}
              </button>
            </form>
          )}

          {/* ZAKŁADKA 3: IMPORT KONFIGURACJI */}
          {activeTab === 'import' && (
            <form onSubmit={handleImport} className="space-y-4">
              <p className="text-xs text-slate-400 leading-relaxed">
                <Trans i18nKey="desc_import">
                  Wczytaj plik <code className="text-indigo-400">.enc</code>, aby nadpisać aktualną konfigurację zadań i połączeń chmurowych.
                </Trans>
              </p>

              <div>
                <label className="block text-slate-400 font-medium mb-1.5 text-xs">
                  {t('lbl_select_enc_file') || 'Plik konfiguracji (.enc)'}
                </label>
                
                {/* Własny, w pełni przetłumaczony selektor plików */}
                <div className="relative flex items-center">
                  <input
                    id="enc-file-input"
                    required
                    type="file"
                    accept=".enc"
                    onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                  <label
                    htmlFor="enc-file-input"
                    className="w-full flex items-center justify-between bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs cursor-pointer hover:border-indigo-500 transition group"
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <FileCode className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                      <span className={`truncate ${importFile ? 'text-white font-medium' : 'text-slate-500'}`}>
                        {importFile ? importFile.name : (t('no_file_chosen') || 'Nie wybrano pliku')}
                      </span>
                    </div>
                    <span className="bg-slate-800 group-hover:bg-slate-700 text-indigo-300 px-2.5 py-1 rounded-lg text-[11px] font-semibold flex-shrink-0 transition">
                      {t('btn_choose_file') || 'Wybierz plik'}
                    </span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 font-medium mb-1.5 text-xs">
                  {t('lbl_import_password') || 'Hasło do odszyfrowania'}
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
                  <input
                    required
                    type="password"
                    value={importPassword}
                    onChange={(e) => setImportPassword(e.target.value)}
                    placeholder={t('ph_import_password') || 'Wpisz hasło do pliku...'}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !importPassword || !importFile}
                className="w-full py-2.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white font-medium text-xs rounded-xl flex items-center justify-center gap-2 transition shadow-md cursor-pointer"
              >
                <Upload className="w-4 h-4" /> {loading ? t('saving_text') : (t('btn_upload_import') || 'Odszyfruj i Przywróć')}
              </button>
            </form>
          )}

        </div>

      </div>
    </div>
  );
}