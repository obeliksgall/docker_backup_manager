import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Shield, Lock, User, Loader2, AlertCircle, CheckCircle2, Globe } from 'lucide-react';

interface LoginProps {
  onLoginSuccess: (token: string, username: string) => void;
}

export default function Login({ onLoginSuccess }: LoginProps) {
  const { t, i18n } = useTranslation();
  
  // Tryby: 'login' lub 'register'
  const [mode, setMode] = useState<'login' | 'register'>('login');
  
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const API_URL = `http://${window.location.hostname}:8000`;

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem('backup_lang', lng);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    // Walidacja powtórzenia hasła po stronie frontendu przy rejestracji
    if (mode === 'register' && password !== confirmPassword) {
      setError(t('confirm_pass_error') || 'Podane hasła nie są identyczne.');
      setLoading(false);
      return;
    }

    const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register';

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Wystąpił błąd autoryzacji.');
      }

      if (mode === 'login') {
        // Logowanie: przekazujemy token do głównego stanu
        onLoginSuccess(data.token, data.username);
      } else {
        // Rejestracja: informujemy o sukcesie i przełączamy na logowanie
        setSuccessMessage(t('register_success_msg') || 'Konto utworzone pomyślnie! Możesz się teraz zalogować.');
        setMode('login');
        setPassword('');
        setConfirmPassword('');
      }
    } catch (err: any) {
      setError(err.message || 'Błąd podczas komunikacji z serwerem.');
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setMode(prev => prev === 'login' ? 'register' : 'login');
    setError(null);
    setSuccessMessage(null);
    setPassword('');
    setConfirmPassword('');
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 antialiased selection:bg-indigo-500/30 text-sm text-slate-300 relative">
      
      {/* SELEKTOR JĘZYKA W PRAWYM GÓRNYM ROGU EKRANU LOGOWANIA */}
      <div className="absolute top-4 right-4 flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs z-50">
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

      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 md:p-8 space-y-6">
        
        {/* BRANDING */}
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="p-3 bg-indigo-600/10 rounded-2xl border border-indigo-500/20 text-indigo-500">
            <Shield className="w-8 h-8" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">Docker Backup Manager</h1>
          <p className="text-xs text-slate-500">
            {mode === 'login' ? t('login_title') : t('register_title')}
          </p>
        </div>

        {/* STATUSY ERROR / SUCCESS */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-xl flex items-center gap-2 text-xs">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <p className="font-medium">{error}</p>
          </div>
        )}

        {successMessage && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-3 rounded-xl flex items-center gap-2 text-xs">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <p className="font-medium">{successMessage}</p>
          </div>
        )}

        {/* FORMULARZ */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-slate-400 font-medium mb-1.5">{t('user_label')}</label>
            <div className="relative">
              <User className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
              <input
                required
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="np. admin"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-400 font-medium mb-1.5">{t('pass_label')}</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
              <input
                required
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
          </div>

          {/* DODATKOWE POLE DLA TRYBU REJESTRACJI */}
          {mode === 'register' && (
            <div className="animate-fade-in">
              <label className="block text-slate-400 font-medium mb-1.5">{t('confirm_pass_label')}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
                <input
                  required
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-white focus:outline-none focus:border-indigo-500 transition"
                />
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 text-white font-medium py-2 rounded-xl flex items-center justify-center gap-2 shadow-md transition pt-2.5 pb-2.5 mt-2"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> {t('loading_text') || 'Przetwarzanie...'}</>
            ) : mode === 'login' ? (
              t('btn_login')
            ) : (
              t('btn_register')
            )}
          </button>
        </form>

        {/* PRZEŁĄCZNIK TRYBÓW NA DOLE */}
        <div className="text-center pt-2 border-t border-slate-800/60">
          <button
            type="button"
            onClick={toggleMode}
            className="text-xs text-indigo-400 hover:text-indigo-300 font-medium transition focus:outline-none"
          >
            {mode === 'login' 
              ? t('toggle_to_register') 
              : t('toggle_to_login')}
          </button>
        </div>

      </div>
    </div>
  );
}