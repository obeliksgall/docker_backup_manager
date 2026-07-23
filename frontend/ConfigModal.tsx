import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Download, Upload, Lock, ShieldCheck, AlertCircle } from 'lucide-react';

interface ConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportSuccess: () => void;
  apiUrl: string;
  getHeaders: () => Record<string, string>;
}

export default function ConfigModal({ isOpen, onClose, onImportSuccess, apiUrl, getHeaders }: ConfigModalProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'export' | 'import'>('export');
  
  const [exportPassword, setExportPassword] = useState('');
  const [importPassword, setImportPassword] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  if (!isOpen) return null;

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
      delete headers['Content-Type']; // Pozwalamy przeglądarce ustawić boundary dla FormData

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
      <div className="bg-slate-900 border border-slate-800 w-full max-w-md rounded-2xl shadow-2xl flex flex-col">
        
        {/* NAGŁÓWEK */}
        <div className="flex justify-between items-center p-5 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-bold text-white">
              {t('modal_config_title') || 'Zarządzanie Konfiguracją'}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* ZAKŁADKI EXPORT / IMPORT */}
        <div className="flex border-b border-slate-800 bg-slate-950/40 p-1">
          <button
            onClick={() => { setActiveTab('export'); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-xl transition flex items-center justify-center gap-2 ${
              activeTab === 'export' ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Download className="w-3.5 h-3.5" /> {t('tab_export') || 'Eksport (Kopia)'}
          </button>
          <button
            onClick={() => { setActiveTab('import'); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-xl transition flex items-center justify-center gap-2 ${
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

          {activeTab === 'export' ? (
            <form onSubmit={handleExport} className="space-y-4">
              <p className="text-xs text-slate-400">
                Pobierz zaszyfrowaną kopię zapasową pliku <code className="text-indigo-400">config.json</code> oraz ustawień połączeń <code className="text-indigo-400">rclone.conf</code>.
              </p>
              <div>
                <label className="block text-slate-400 font-medium mb-1.5 text-xs">{t('lbl_export_password') || 'Hasło do zaszyfrowania pliku'}</label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
                  <input
                    required
                    type="password"
                    value={exportPassword}
                    onChange={(e) => setExportPassword(e.target.value)}
                    placeholder="Wpisz bezpieczne hasło..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={loading || !exportPassword}
                className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium text-xs rounded-xl flex items-center justify-center gap-2 transition shadow-md"
              >
                <Download className="w-4 h-4" /> {loading ? t('saving_text') : (t('btn_download_export') || 'Pobierz zaszyfrowany plik')}
              </button>
            </form>
          ) : (
            <form onSubmit={handleImport} className="space-y-4">
              <p className="text-xs text-slate-400">
                Wczytaj plik <code className="text-indigo-400">.enc</code>, aby nadpisać aktualną konfigurację zadań i połączeń chmurowych.
              </p>
              <div>
                <label className="block text-slate-400 font-medium mb-1.5 text-xs">{t('lbl_select_enc_file') || 'Plik konfiguracji (.enc)'}</label>
                <input
                  required
                  type="file"
                  accept=".enc"
                  onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-300 file:mr-3 file:py-1 file:px-2 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-indigo-400 hover:file:bg-slate-700 cursor-pointer"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1.5 text-xs">{t('lbl_import_password') || 'Hasło do odszyfrowania'}</label>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
                  <input
                    required
                    type="password"
                    value={importPassword}
                    onChange={(e) => setImportPassword(e.target.value)}
                    placeholder="Wpisz hasło do pliku..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={loading || !importPassword || !importFile}
                className="w-full py-2.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white font-medium text-xs rounded-xl flex items-center justify-center gap-2 transition shadow-md"
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