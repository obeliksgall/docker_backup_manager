import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Folder, FolderPlus, ChevronLeft, Loader2 } from 'lucide-react';

const API_KEY = import.meta.env.VITE_API_KEY;
const API_URL = `http://${window.location.hostname}:8000`;

interface NASDirectory {
  name: string;
  path: string;
}

interface FolderBrowserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  title: string;
  initialPath?: string;
}

export default function FolderBrowserModal({ isOpen, onClose, onSelect, title, initialPath }: FolderBrowserModalProps) {
  const { t } = useTranslation();
  
  const getCleanPathForApi = (path: string | undefined) => {
    if (!path || path.trim() === '') return '/';
    if (path.startsWith('/storage')) {
      const cleaned = path.replace('/storage', '');
      return cleaned === '' ? '/' : cleaned;
    }
    return path;
  };

  const [currentPath, setCurrentPath] = useState('/');
  const [folders, setFolders] = useState<NASDirectory[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFolders = async (path: string) => {
    setLoading(true);
    setError(null);
    const safePath = path.trim() === '' ? '/' : path;

    try {
      const response = await fetch(`${API_URL}/api/browse?path=${encodeURIComponent(safePath)}`, {
        headers: { 'X-API-Key': API_KEY }
      });
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || t('error_folder_fetch'));
      }
      
      if (data && Array.isArray(data.directories)) {
        setFolders(data.directories);
        setCurrentPath(data.current_path || safePath);
      } else {
        throw new Error(t('error_folder_format'));
      }
    } catch (err: any) {
      setError(err.message || 'Error');
      setFolders([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      const apiPath = getCleanPathForApi(initialPath);
      fetchFolders(apiPath);
    }
  }, [isOpen, initialPath]);

  if (!isOpen) return null;

  const handleFolderClick = (clickedFolder: NASDirectory) => {
    fetchFolders(clickedFolder.path);
  };

  const handleGoBack = () => {
    if (currentPath === '/') return;
    const parts = currentPath.split('/').filter(p => p !== '');
    parts.pop();
    const newPath = '/' + parts.join('/');
    fetchFolders(newPath);
  };

  const handleConfirm = () => {
    let finalPath = currentPath;
    if (!finalPath.startsWith('/storage')) {
      finalPath = '/storage' + (finalPath === '/' ? '' : finalPath);
    }
    if (finalPath === '') finalPath = '/storage';
    
    onSelect(finalPath);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-lg rounded-xl shadow-2xl flex flex-col h-[70vh]">
        
        {/* NAGŁÓWEK */}
        <div className="flex justify-between items-center p-4 border-b border-slate-800">
          <div>
            <h3 className="text-base font-bold text-white">{title}</h3>
            <p className="text-xs text-indigo-400 font-mono truncate max-w-[400px] mt-0.5">
              /storage{currentPath === '/' ? '' : currentPath}
            </p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* ZAWARTOŚĆ */}
        <div className="flex-1 overflow-y-auto p-4 space-y-1 text-sm text-slate-300">
          {error && (
            <div className="text-red-400 bg-red-500/10 border border-red-500/20 p-3 rounded-lg text-xs mb-2">
              {error}
            </div>
          )}

          {currentPath !== '/' && (
            <button
              onClick={handleGoBack}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-800/60 rounded-xl transition text-slate-400 text-left font-medium"
            >
              <ChevronLeft className="w-4 h-4" /> {t('browser_go_up')}
            </button>
          )}

          {loading ? (
            <div className="flex justify-center items-center py-12 text-slate-500 gap-2 text-xs">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-500" /> {t('browser_loading')}
            </div>
          ) : folders.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs">{t('browser_empty')}</div>
          ) : (
            folders.map((folder, idx) => (
              <button
                key={idx}
                onClick={() => handleFolderClick(folder)}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-slate-800 rounded-xl transition text-left text-slate-200 group"
              >
                <Folder className="w-4 h-4 text-amber-500 group-hover:scale-105 transition" />
                <span className="truncate">{folder.name}</span>
              </button>
            ))
          )}
        </div>

        {/* STOPKA */}
        <div className="p-3 bg-slate-950/40 border-t border-slate-800 flex justify-end gap-2 rounded-b-xl">
          <button onClick={onClose} className="px-4 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition">{t('btn_cancel')}</button>
          <button onClick={handleConfirm} className="px-4 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg flex items-center gap-1.5 font-medium transition">
            <FolderPlus className="w-3.5 h-3.5" /> {t('btn_select_folder')}
          </button>
        </div>

      </div>
    </div>
  );
}