import { useTranslation } from 'react-i18next';
import { X, Terminal, RefreshCw } from 'lucide-react';

interface LogModalProps {
  isOpen: boolean;
  onClose: () => void;
  taskName: string;
  logs: string;
  loading: boolean;
  onRefresh: () => void;
}

export default function LogModal({ isOpen, onClose, taskName, logs, loading, onRefresh }: LogModalProps) {
  const { t } = useTranslation();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-4xl rounded-2xl shadow-2xl flex flex-col h-[80vh]">
        
        {/* NAGŁÓWEK */}
        <div className="flex justify-between items-center p-4 border-b border-slate-800">
          <div className="flex items-center gap-2 text-white">
            <Terminal className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold">{t('log_title')} <span className="text-indigo-400">{taskName}</span></h2>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={onRefresh}
              disabled={loading}
              className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg transition"
              title={t('tooltip_refresh_logs') || ''}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={onClose} className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg transition">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* OKNO TERMINALA */}
        <div className="p-4 flex-1 bg-slate-950 overflow-auto font-mono text-xs text-slate-300 leading-relaxed rounded-b-2xl select-text">
          {loading ? (
            <div className="text-center py-12 text-slate-500 animate-pulse">{t('log_loading')}</div>
          ) : (
            <pre className="whitespace-pre-wrap break-all bg-transparent border-0 p-0 m-0 text-emerald-400">
              {logs || t('log_empty')}
            </pre>
          )}
        </div>

      </div>
    </div>
  );
}