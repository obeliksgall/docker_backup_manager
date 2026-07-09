import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Server, Cloud, FolderOpen } from 'lucide-react';
import FolderBrowserModal from './FolderBrowserModal';

interface Task {
  id?: number;
  name: string;
  source: string;
  destination: string;
  type: 'local' | 'cloud';
  mode: string;
  schedule: string;
  enabled: boolean;
  restore_enabled: boolean;
  exclude: string[];
  custom_flags: string[]; // <-- NOWE POLE W INTERFEJSIE
  retention_days: number;
  discord_webhook?: string;
  ntfy_url?: string;
}

interface TaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (taskData: any) => Promise<void>;
  task?: Task | null;
}

export default function TaskModal({ isOpen, onClose, onSave, task }: TaskModalProps) {
  const { t } = useTranslation();
  
  const [formData, setFormData] = useState<Task>({
    name: '', source: '', destination: '', type: 'local', mode: 'mirror',
    schedule: '0 3 * * *', enabled: true, restore_enabled: false, exclude: [],
    custom_flags: [], retention_days: 0, discord_webhook: '', ntfy_url: ''
  });

  const [excludeInput, setExcludeInput] = useState('');
  const [customFlagsInput, setCustomFlagsInput] = useState(''); // <-- STAN DLA INPUTU FLAG
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [isBrowserOpen, setIsBrowserOpen] = useState(false);
  const [browserTarget, setBrowserTarget] = useState<'source' | 'destination'>('source');
  const [browserTitle, setBrowserTitle] = useState('');

  useEffect(() => {
    if (task) {
      setFormData({
        ...task,
        discord_webhook: task.discord_webhook || '',
        ntfy_url: task.ntfy_url || '',
        custom_flags: task.custom_flags || []
      });
      setExcludeInput(task.exclude ? task.exclude.join(', ') : '');
      setCustomFlagsInput(task.custom_flags ? task.custom_flags.join(', ') : ''); // <-- ŁADOWANIE FLAG DO EDYCJI
    } else {
      setFormData({
        name: '', source: '', destination: '', type: 'local', mode: 'mirror',
        schedule: '0 3 * * *', enabled: true, restore_enabled: false, exclude: [],
        custom_flags: [], retention_days: 0, discord_webhook: '', ntfy_url: ''
      });
      setExcludeInput('');
      setCustomFlagsInput(''); // <-- CZYSZCZENIE INPUTU
    }
  }, [task, isOpen]);

  if (!isOpen) return null;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    const val = type === 'checkbox' ? (e.target as HTMLInputElement).checked : value;
    
    setFormData(prev => ({
      ...prev,
      [name]: name === 'retention_days' ? parseInt(value) || 0 : val
    }));
  };

  const openBrowser = (target: 'source' | 'destination', titleKey: string) => {
    setBrowserTarget(target);
    setBrowserTitle(t(titleKey));
    setIsBrowserOpen(true);
  };

  const handleFolderSelect = (selectedPath: string) => {
    setFormData(prev => ({
      ...prev,
      [browserTarget]: selectedPath
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    // Konwersja inputów tekstowych na tablice stringów
    const excludeArray = excludeInput.split(',').map(item => item.trim()).filter(item => item !== '');
    const flagsArray = customFlagsInput.split(',').map(item => item.trim()).filter(item => item !== '');

    try {
      await onSave({ ...formData, exclude: excludeArray, custom_flags: flagsArray });
      onClose();
    } catch (err) {
      // log błędu
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-2xl rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">
        
        {/* NAGŁÓWEK */}
        <div className="flex justify-between items-center p-5 border-b border-slate-800">
          <h2 className="text-xl font-bold text-white">
            {task ? t('modal_edit_title') : t('modal_create_title')}
          </h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* FORMULARZ */}
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto space-y-4 flex-1 text-sm text-slate-300">
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_copy_type')}</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setFormData(p => ({ ...p, type: 'local' }))}
                  className={`py-2 px-3 rounded-xl border font-medium flex items-center justify-center gap-2 transition ${
                    formData.type === 'local' ? 'bg-emerald-500/10 border-emerald-500 text-emerald-400' : 'border-slate-800 bg-slate-950 text-slate-400'
                  }`}
                >
                  <Server className="w-4 h-4" /> {t('lbl_local_rsync')}
                </button>
                <button
                  type="button"
                  onClick={() => setFormData(p => ({ ...p, type: 'cloud' }))}
                  className={`py-2 px-3 rounded-xl border font-medium flex items-center justify-center gap-2 transition ${
                    formData.type === 'cloud' ? 'bg-blue-500/10 border-blue-500 text-blue-400' : 'border-slate-800 bg-slate-950 text-slate-400'
                  }`}
                >
                  <Cloud className="w-4 h-4" /> {t('lbl_cloud_rclone')}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_task_name')}</label>
              <input
                required type="text" name="name" value={formData.name} onChange={handleChange}
                placeholder={t('ph_task_name') || ''}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_src_dir')}</label>
              <div className="flex gap-2">
                <input
                  required type="text" name="source" value={formData.source} onChange={handleChange}
                  placeholder={t('ph_src_dir') || ''}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition text-sm"
                />
                <button
                  type="button"
                  onClick={() => openBrowser('source', 'browser_src_title')}
                  className="px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition flex items-center justify-center gap-1.5 text-xs font-medium border border-slate-700"
                >
                  <FolderOpen className="w-4 h-4 text-indigo-400" /> {t('btn_browse')}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_dest_dir')}</label>
              <div className="flex gap-2">
                <input
                  required type="text" name="destination" value={formData.destination} onChange={handleChange}
                  placeholder={formData.type === 'cloud' ? 'np. gdrive:/backup' : 'np. /storage/backup_lokalny'}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition text-sm"
                />
                {formData.type === 'local' && (
                  <button
                    type="button"
                    onClick={() => openBrowser('destination', 'browser_dest_title')}
                    className="px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition flex items-center justify-center gap-1.5 text-xs font-medium border border-slate-700"
                  >
                    <FolderOpen className="w-4 h-4 text-indigo-400" /> {t('btn_browse')}
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_sync_mode')}</label>
              <select
                name="mode" value={formData.mode} onChange={handleChange}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
              >
                <option value="mirror">{t('mode_mirror')}</option>
                <option value="copy">{t('mode_copy')}</option>
                <option value="move">{t('mode_move')}</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_cron')}</label>
              <input
                required type="text" name="schedule" value={formData.schedule} onChange={handleChange}
                placeholder={t('ph_cron') || ''}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_retention')}</label>
              <input
                type="number" name="retention_days" value={formData.retention_days} onChange={handleChange} min="0"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-400 font-medium mb-1.5">{t('lbl_exclusions')}</label>
            <input
              type="text" value={excludeInput} onChange={(e) => setExcludeInput(e.target.value)}
              placeholder={t('ph_exclusions') || ''}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
            />
          </div>

          {/* DYNAMICZNE POLE DLA FLAG RCLONE PER ZADANIE */}
          {formData.type === 'cloud' && (
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">Custom Rclone Flags (rozdziel przecinkami)</label>
              <input
                type="text" value={customFlagsInput} onChange={(e) => setCustomFlagsInput(e.target.value)}
                placeholder="np. --buffer-size=32M, --transfers=4, --bwlimit=10M"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition font-mono text-xs text-indigo-400"
              />
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-800/60">
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">Discord Webhook URL</label>
              <input
                type="text" name="discord_webhook" value={formData.discord_webhook} onChange={handleChange}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
            <div>
              <label className="block text-slate-400 font-medium mb-1.5">Ntfy Topic URL</label>
              <input
                type="text" name="ntfy_url" value={formData.ntfy_url} onChange={handleChange}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
          </div>

          <div className="flex gap-6 pt-2">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" name="enabled" checked={formData.enabled} onChange={handleChange} className="w-4 h-4 bg-slate-950 border border-slate-800 rounded text-indigo-600 focus:ring-0" />
              <span className="font-medium text-slate-300">{t('lbl_cron_active')}</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" name="restore_enabled" checked={formData.restore_enabled} onChange={handleChange} className="w-4 h-4 bg-slate-950 border border-slate-800 rounded text-indigo-600 focus:ring-0" />
              <span className="font-medium text-slate-300">{t('lbl_allow_restore')}</span>
            </label>
          </div>

        </form>

        {/* STOPKA */}
        <div className="p-4 bg-slate-950/40 border-t border-slate-800 flex justify-end gap-3 rounded-b-2xl">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition">{t('btn_cancel')}</button>
          <button type="submit" onClick={handleSubmit} disabled={isSubmitting} className="px-5 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 text-white rounded-xl flex items-center gap-1.5 shadow-md transition">
            <Save className="w-4 h-4" /> {isSubmitting ? t('saving_text') : t('btn_save_changes')}
          </button>
        </div>

      </div>

      <FolderBrowserModal
        isOpen={isBrowserOpen}
        onClose={() => setIsBrowserOpen(false)}
        title={browserTitle}
        initialPath={formData[browserTarget] || '/'}
        onSelect={handleFolderSelect}
      />
    </div>
  );
}