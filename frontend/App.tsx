import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Shield, RefreshCw, Server, Cloud, Play, CheckCircle, XCircle, 
  Edit2, Trash2, Loader2, Plus, FileText, LogOut, Globe, Database,
  Copy, Settings
} from 'lucide-react';
import TaskModal from './TaskModal';
import LogModal from './LogModal';
import Login from './Login';
import ConfigModal from './ConfigModal';

const API_URL = `http://${window.location.hostname}:8000`;

interface Task {
  id: number;
  name: string;
  source: string;
  destination: string;
  type: 'local' | 'cloud';
  mode: string;
  schedule: string;
  enabled: boolean;
  restore_enabled: boolean;
  exclude: string[];
  custom_flags: string[];
  next_task_id?: number | null;
  retention_days: number;
  status?: string;
  discord_webhook?: string;
  ntfy_url?: string;
  last_run?: string | null;
}

export default function App() {
  const { t, i18n } = useTranslation();

  // PRZECHOWYWANIE SESJI UŻYTKOWNIKA
  const [token, setToken] = useState<string | null>(localStorage.getItem('backup_auth_token'));
  const [username, setUsername] = useState<string | null>(localStorage.getItem('backup_auth_user'));

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningTasks, setRunningTasks] = useState<{ [key: number]: boolean }>({});

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const [isLogModalOpen, setIsLogModalOpen] = useState(false);
  const [activeLogTask, setActiveLogTask] = useState<Task | null>(null);
  const [logsText, setLogsText] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);

  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem('backup_lang', lng);
  };

  const getHeaders = () => {
    return {
      'Content-Type': 'application/json',
      'X-API-Key': import.meta.env.VITE_API_KEY || 'DomyślnyKluczBezpieczeństwa'
    };
  };

  const handleLoginSuccess = (newToken: string, newUsername: string) => {
    localStorage.setItem('backup_auth_token', newToken);
    localStorage.setItem('backup_auth_user', newUsername);
    setToken(newToken);
    setUsername(newUsername);
  };

  const handleLogout = () => {
    localStorage.removeItem('backup_auth_token');
    localStorage.removeItem('backup_auth_user');
    setToken(null);
    setUsername(null);
    setTasks([]);
  };

  const fetchTasks = async () => {
    if (!token) return;
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/tasks`, {
        headers: getHeaders()
      });
      
      if (response.status === 403) {
        handleLogout();
        return;
      }
      
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Błąd API: ${response.status}`);
      
      if (data && Array.isArray(data.tasks)) {
        setTasks(data.tasks);
        setError(null);
      } else {
        throw new Error("Otrzymano nieprawidłowy format danych z serwera.");
      }
    } catch (err: any) {
      setError(err.message || 'Nie udało się połączyć z API');
      setTasks([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchLogs = async (task: Task) => {
    setActiveLogTask(task);
    setIsLogModalOpen(true);
    setLogsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/tasks/${task.id}/logs`, {
        headers: getHeaders()
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Błąd pobierania logów');
      setLogsText(data.logs);
    } catch (err: any) {
      setLogsText(`Błąd: ${err.message}`);
    } finally {
      setLogsLoading(false);
    }
  };

  const runTask = async (id: number) => {
    if (runningTasks[id]) return;
    setRunningTasks(prev => ({ ...prev, [id]: true }));
    try {
      const response = await fetch(`${API_URL}/api/tasks/${id}/run`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Nie udało się uruchomić zadania.");
      }
      alert(t('task_queued_alert') || "Zadanie przekazane do kolejki NAS (wykonywanie jedno po drugim).");
      fetchTasks();
    } catch (err: any) {
      alert(`Błąd uruchamiania: ${err.message}`);
    } finally {
      setRunningTasks(prev => ({ ...prev, [id]: false }));
    }
  };

  const stopTask = async (id: number) => {
    if (!confirm(t('stop_confirm_msg') || "Czy na pewno chcesz wymusić zatrzymanie tego zadania?")) return;
    try {
      const response = await fetch(`${API_URL}/api/tasks/${id}/stop`, {
        method: 'POST',
        headers: getHeaders()
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nie udało się zatrzymać zadania.");
      alert(data.message);
      fetchTasks();
    } catch (err: any) {
      alert(`Błąd zatrzymywania: ${err.message}`);
    }
  };

  const handleSaveTask = async (taskData: any) => {
    const isEdit = !!taskData.id;
    const url = isEdit ? `${API_URL}/api/tasks/${taskData.id}` : `${API_URL}/api/tasks`;
    const method = isEdit ? 'PUT' : 'POST';

    const response = await fetch(url, {
      method: method,
      headers: getHeaders(),
      body: JSON.stringify(taskData)
    });

    if (!response.ok) {
      const errData = await response.json();
      alert(`Błąd zapisu: ${errData.detail || 'Nieznany błąd serwera'}`);
      throw new Error("Save failed");
    }
    fetchTasks();
  };

  const handleDeleteTask = async (id: number, name: string) => {
    if (!confirm(t('delete_confirm_msg', { name }) || `Czy na pewno chcesz bezpowrotnie usunąć zadanie: "${name}"?`)) return;
    try {
      const response = await fetch(`${API_URL}/api/tasks/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Nie udało się usunąć.');
      }
      fetchTasks();
    } catch (err: any) {
      alert(`Błąd: ${err.message}`);
    }
  };

  const handleRestore = async (task: Task) => {
    if (!task.restore_enabled) {
      alert(t('restore_disabled_alert', { name: task.name }) || `Operacja zablokowana. Włącz opcję "Zezwól na operacje Restore" w edycji zadania "${task.name}".`);
      return;
    }
    const confirmMessage = t('restore_confirm_msg', { name: task.name }) || `⚠️ UWAGA! Rozpoczynasz procedurę przywracania danych dla zadania: "${task.name}".\n\nCzy na pewno chcesz kontynuować?`;
    if (!confirm(confirmMessage)) return;

    try {
      const response = await fetch(`${API_URL}/api/tasks/${task.id}/restore`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Nie udało się uruchomić przywracania.");
      }
      alert(t('restore_queued_alert') || `Procedura Restore została pomyślnie dodana do kolejki!`);
      fetchTasks();
    } catch (err: any) {
      alert(`Błąd przywracania: ${err.message}`);
    }
  };

  useEffect(() => {
    if (!token) return;

    fetchTasks();

    const interval = setInterval(() => {
      const hasRunningTasks = tasks.some(task => task.status === 'RUNNING');
      
      if (hasRunningTasks) {
        fetchTasks();
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [token, tasks]);

  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 antialiased selection:bg-indigo-500/30">
      
      <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          
          <div className="flex items-center gap-2.5 select-none">
            <Database className="w-6 h-6 text-indigo-500" />
            <span className="font-bold text-lg tracking-tight text-white">Docker Backup Manager</span>
          </div>

          <div className="flex items-center gap-4">
            
            <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-lg p-1 text-xs">
              <Globe className="w-3.5 h-3.5 text-slate-500 ml-1" />
              <button 
                type="button"
                onClick={() => changeLanguage('pl')} 
                className={`px-2 py-0.5 rounded font-medium transition ${i18n.language.startsWith('pl') ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
              >
                PL
              </button>
              <button 
                type="button"
                onClick={() => changeLanguage('en')} 
                className={`px-2 py-0.5 rounded font-medium transition ${i18n.language.startsWith('en') ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
              >
                EN
              </button>
            </div>

            <div className="text-right hidden sm:block border-l border-slate-800 pl-4 select-none">
              <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-500">{t('logged_in_as')}</p>
              <p className="text-sm font-medium text-slate-200">{username}</p>
            </div>

            <button 
              onClick={handleLogout} 
              className="p-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-xl transition"
              title={t('btn_logout') || 'Wyloguj się'}
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>

        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        
        <div className="flex items-center justify-between border-b border-slate-900 pb-4">
          <h2 className="text-xl font-bold text-white tracking-tight">{t('dashboard_title') || 'Zadania automatyczne'}</h2>
          <div className="flex gap-2">
            {/* PRZYCISK ZARZĄDZANIA KONFIGURACJĄ */}
            <button 
              onClick={() => setIsConfigModalOpen(true)}
              className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-2 rounded-xl text-sm font-medium hover:bg-slate-800 transition text-slate-300 hover:text-white"
              title={t('tooltip_config_modal') || 'Kopia/Przywracanie ustawień'}
            >
              <Settings className="w-4 h-4 text-indigo-400" />
              <span className="hidden sm:inline">{t('btn_config_settings') || 'Ustawienia'}</span>
            </button>
            
            <button 
              onClick={fetchTasks}
              className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-4 py-2 rounded-xl text-sm font-medium hover:bg-slate-800 transition"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> {t('btn_refresh')}
            </button>
            <button 
              onClick={() => { setSelectedTask(null); setIsModalOpen(true); }}
              className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-sm font-medium transition shadow-lg shadow-indigo-600/10"
            >
              <Plus className="w-4 h-4" /> {t('btn_new_task')}
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl flex items-center gap-3">
            <XCircle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {loading && tasks.length === 0 ? (
          <div className="text-center py-12 text-slate-400 font-medium flex items-center justify-center gap-2">
            <Loader2 className="w-5 h-5 animate-spin text-indigo-500" /> {t('loading_text')}
          </div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-16 bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl text-slate-500">
            {t('no_tasks') || 'Brak zdefiniowanych zadań backupu.'}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {tasks.map((task) => (
              <div key={task.id} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700/80 transition flex flex-col justify-between shadow-xl relative group">
                
                {/* Przyciski operacyjne w rogu karty */}
                <div className="absolute top-5 right-5 flex gap-1 opacity-40 group-hover:opacity-100 transition">
                  <button onClick={() => fetchLogs(task)} className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-emerald-400 rounded-lg transition" title={t('tooltip_logs') || 'Logi'}>
                    <FileText className="w-4 h-4" />
                  </button>
                  
                  {/* KLONOWANIE ZADANIA */}
                  <button 
                    onClick={() => {
                      if (task.status !== 'RUNNING') {
                        const clonedTask = { 
                          ...task, 
                          id: undefined as unknown as number, 
                          name: `${task.name} (${t('cloned_suffix') || 'Kopia'})`,
                          status: 'New'
                        };
                        setSelectedTask(clonedTask);
                        setIsModalOpen(true);
                      }
                    }} 
                    disabled={task.status === 'RUNNING'}
                    className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-amber-400 rounded-lg transition disabled:opacity-30 disabled:hover:text-slate-400 disabled:cursor-not-allowed" 
                    title={t('tooltip_clone') || 'Klonuj zadanie'}
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                  
                  <button 
                    onClick={() => { if(task.status !== 'RUNNING') { setSelectedTask(task); setIsModalOpen(true); } }} 
                    disabled={task.status === 'RUNNING'}
                    className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-indigo-400 rounded-lg transition disabled:opacity-30 disabled:hover:text-slate-400 disabled:cursor-not-allowed" 
                    title={task.status === 'RUNNING' ? '' : (t('tooltip_edit') || 'Edytuj')}
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  
                  <button 
                    onClick={() => { if(task.status !== 'RUNNING') handleDeleteTask(task.id, task.name); }} 
                    disabled={task.status === 'RUNNING'}
                    className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-red-400 rounded-lg transition disabled:opacity-30 disabled:hover:text-slate-400 disabled:cursor-not-allowed" 
                    title={task.status === 'RUNNING' ? '' : (t('tooltip_delete') || 'Usuń')}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="bg-slate-950 text-indigo-400 font-mono text-[10px] px-1.5 py-0.5 rounded border border-slate-800/60 font-bold" title="Task ID">
                      #{task.id}
                    </span>
                    <h3 className="font-bold text-base text-white truncate max-w-[180px]">{task.name}</h3>
                  </div>
                  <div className="mb-4">
                    <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold inline-flex items-center gap-1.5 border ${
                      task.type === 'cloud' ? 'bg-blue-500/5 text-blue-400 border-blue-500/10' : 'bg-emerald-500/5 text-emerald-400 border-emerald-500/10'
                    }`}>
                      {task.type === 'cloud' ? <Cloud className="w-3 h-3" /> : <Server className="w-3 h-3" />}
                      {task.type.toUpperCase()}
                    </span>
                    {!task.enabled && (
                      <span className="ml-2 px-2.5 py-0.5 rounded-full text-[11px] font-bold inline-flex items-center bg-slate-950 text-slate-500 border border-slate-800">
                        {t('task_paused') || 'Wstrzymane'}
                      </span>
                    )}
                  </div>
                  
                  <div className="space-y-1.5 text-xs text-slate-400 mb-4 font-normal">
                    <p className="truncate"><span className="text-slate-500 font-medium">{t('lbl_source') || 'Źródło'}:</span> {task.source}</p>
                    <p className="truncate"><span className="text-slate-500 font-medium">{t('lbl_destination') || 'Cel'}:</span> {task.destination}</p>
                    <p><span className="text-slate-500 font-medium">{t('lbl_mode') || 'Tryb'}:</span> <span className="text-slate-300 font-medium">{task.mode}</span></p>
                    <p><span className="text-slate-500 font-medium">Cron:</span> <code className="bg-slate-950 px-1.5 py-0.5 rounded font-mono text-[11px] text-indigo-400 border border-slate-800/40">{task.schedule}</code></p>
                    
                    {/* DYNAMICZNE WYŚWIETLANIE DATY OSTATNIEGO URUCHOMIENIA */}
                    <p>
                      <span className="text-slate-500 font-medium">{t('lbl_last_run') || 'Ostatnie uruchomienie'}:</span>{' '}
                      <span className={task.last_run ? 'text-slate-300 font-medium' : 'text-slate-600 italic'}>
                        {task.last_run ? task.last_run : (t('status_never') || 'Nieuruchamiane')}
                      </span>
                    </p>
                  </div>
                </div>

                {/* Stopka karty z przyciskiem STOP */}
                <div className="border-t border-slate-800/60 pt-4 mt-2 flex justify-between items-center gap-2 select-none">
                  <div className="flex items-center gap-1.5 text-xs">
                    {task.status === 'RUNNING' ? (
                      <span className="text-indigo-400 flex items-center gap-1 font-semibold animate-pulse"><Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('status_processing') || 'W trakcie...'}</span>
                    ) : task.status === 'OK' || task.status === 'SUKCES' || task.status === 'SUCCESS' ? (
                      <span className="text-emerald-400 flex items-center gap-1 font-semibold"><CheckCircle className="w-3.5 h-3.5" /> {t('status_success') || 'Sukces'}</span>
                    ) : task.status === 'Zatrzymane' || task.status === 'STOPPED' ? (
                      <span className="text-amber-400 flex items-center gap-1 font-semibold"><XCircle className="w-3.5 h-3.5 text-amber-500" /> {task.status}</span>
                    ) : task.status ? (
                      <span className="text-red-400 flex items-center gap-1 font-semibold"><XCircle className="w-3.5 h-3.5" /> {t('status_error') || 'Błąd'}</span>
                    ) : (
                      <span className="text-slate-500 font-medium">{t('status_never') || 'Nieuruchamiane'}</span>
                    )}
                  </div>
                  
                  <div className="flex gap-2">
                    {task.status === 'RUNNING' ? (
                      <button 
                        onClick={() => stopTask(task.id)} 
                        className="bg-red-600 hover:bg-red-500 text-white px-3 py-1.5 rounded-xl text-xs font-semibold transition flex items-center gap-1 shadow-sm shadow-red-600/10 cursor-pointer"
                        title="Zatrzymaj proces rclone/rsync"
                      >
                        <XCircle className="w-3 h-3" /> Stop
                      </button>
                    ) : (
                      <button 
                        onClick={() => handleRestore(task)} 
                        disabled={runningTasks[task.id]}
                        className="bg-slate-800 hover:bg-slate-700 disabled:bg-slate-900 disabled:text-slate-600 disabled:border-slate-800/40 text-slate-300 px-3 py-1.5 rounded-xl text-xs font-semibold transition border border-slate-700/40 cursor-pointer disabled:cursor-not-allowed"
                      >
                        Restore
                      </button>
                    )}
                    
                    <button 
                      onClick={() => runTask(task.id)}
                      disabled={runningTasks[task.id] || task.status === 'RUNNING'}
                      className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 disabled:border disabled:border-slate-700/50 text-white px-3 py-1.5 rounded-xl text-xs font-semibold transition shadow-sm flex items-center gap-1.5"
                    >
                      {runningTasks[task.id] || task.status === 'RUNNING' ? (
                        <><Loader2 className="w-3 h-3 animate-spin text-indigo-400" /> {t('status_processing') || 'W trakcie...'}</>
                      ) : (
                        <><Play className="w-3 h-3 fill-current flex-shrink-0" /> {t('lbl_run') || 'Uruchom'}</>
                      )}
                    </button>
                  </div>
                </div>

              </div>
            ))}
          </div>
        )}

      </main>

      <TaskModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSave={handleSaveTask} task={selectedTask} />
      <LogModal isOpen={isLogModalOpen} onClose={() => setIsLogModalOpen(false)} taskName={activeLogTask ? activeLogTask.name : ''} logs={logsText} loading={logsLoading} onRefresh={() => activeLogTask && fetchLogs(activeLogTask)} />
      <ConfigModal 
        isOpen={isConfigModalOpen} 
        onClose={() => setIsConfigModalOpen(false)} 
        onImportSuccess={fetchTasks} 
        apiUrl={API_URL} 
        getHeaders={getHeaders} 
      />
    </div>
  );
}