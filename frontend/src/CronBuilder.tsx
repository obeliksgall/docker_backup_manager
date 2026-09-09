import React, { useState, useEffect } from 'react';
import { Clock, Calendar, Sliders, PlayCircle, Check, Info } from 'lucide-react';

interface CronBuilderProps {
  value: string;
  onChange: (value: string) => void;
  lang?: string;
}

type Mode = 'daily' | 'hourly' | 'interval' | 'weekdays' | 'manual' | 'custom';

export default function CronBuilder({ value, onChange, lang = 'pl' }: CronBuilderProps) {
  const isPl = lang.startsWith('pl');

  // Detect mode from initial cron value
  const detectMode = (cron: string): { mode: Mode; hour: string; minute: string; interval: string; days: string } => {
    const trimmed = (cron || '').trim();
    if (!trimmed) {
      return { mode: 'manual', hour: '03', minute: '00', interval: '4', days: '1-5' };
    }
    const parts = trimmed.split(/\s+/);
    if (parts.length === 5) {
      const [m, h, dom, mon, dow] = parts;
      if (dom === '*' && mon === '*') {
        if (h === '*' && m === '0') {
          return { mode: 'hourly', hour: '00', minute: '00', interval: '1', days: '1-5' };
        }
        if (h.startsWith('*/') && m === '0') {
          return { mode: 'interval', hour: '00', minute: '00', interval: h.replace('*/', ''), days: '1-5' };
        }
        if (dow === '*' && /^\d+$/.test(h) && /^\d+$/.test(m)) {
          return { mode: 'daily', hour: h.padStart(2, '0'), minute: m.padStart(2, '0'), interval: '4', days: '1-5' };
        }
        if (dow !== '*' && /^\d+$/.test(h) && /^\d+$/.test(m)) {
          return { mode: 'weekdays', hour: h.padStart(2, '0'), minute: m.padStart(2, '0'), interval: '4', days: dow };
        }
      }
    }
    return { mode: 'custom', hour: '03', minute: '00', interval: '4', days: '1-5' };
  };

  const initial = detectMode(value);
  const [mode, setMode] = useState<Mode>(initial.mode);
  const [hour, setHour] = useState(initial.hour);
  const [minute, setMinute] = useState(initial.minute);
  const [intervalHours, setIntervalHours] = useState(initial.interval);
  const [weekdaysPreset, setWeekdaysPreset] = useState(initial.days);
  const [customCron, setCustomCron] = useState(value);

  // Sync internal state when prop changes from outside
  useEffect(() => {
    const detected = detectMode(value);
    setMode(detected.mode);
    if (detected.mode !== 'custom') {
      setHour(detected.hour);
      setMinute(detected.minute);
      setIntervalHours(detected.interval);
      setWeekdaysPreset(detected.days);
    }
    setCustomCron(value);
  }, [value]);

  const updateCron = (newMode: Mode, newH: string, newM: string, newInt: string, newDays: string) => {
    let generated = '';
    const hNum = parseInt(newH, 10) || 0;
    const mNum = parseInt(newM, 10) || 0;

    switch (newMode) {
      case 'daily':
        generated = `${mNum} ${hNum} * * *`;
        break;
      case 'hourly':
        generated = `${mNum} * * * *`;
        break;
      case 'interval':
        generated = `0 */${newInt} * * *`;
        break;
      case 'weekdays':
        generated = `${mNum} ${hNum} * * ${newDays}`;
        break;
      case 'manual':
        generated = '';
        break;
      case 'custom':
        generated = customCron;
        break;
    }
    onChange(generated);
  };

  const handleModeChange = (m: Mode) => {
    setMode(m);
    updateCron(m, hour, minute, intervalHours, weekdaysPreset);
  };

  const getHumanDescription = () => {
    if (!value || !value.trim()) {
      return isPl 
        ? 'Uruchamianie wyłącznie na żądanie (ręcznie przyciskiem Start).' 
        : 'Manual execution only (on-demand via Run button).';
    }
    const parts = value.trim().split(/\s+/);
    if (parts.length !== 5) {
      return isPl ? `Niestandardowy zapis: ${value}` : `Custom cron: ${value}`;
    }
    const [m, h, dom, mon, dow] = parts;
    if (dom === '*' && mon === '*') {
      if (h === '*') {
        return isPl ? `Uruchamia się co godzinę w minucie ${m}.` : `Runs every hour at minute ${m}.`;
      }
      if (h.startsWith('*/')) {
        return isPl ? `Uruchamia się co ${h.replace('*/', '')} godz.` : `Runs every ${h.replace('*/', '')} hours.`;
      }
      const timeStr = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`;
      if (dow === '*') {
        return isPl ? `Uruchamia się codziennie o ${timeStr}.` : `Runs daily at ${timeStr}.`;
      }
      if (dow === '1-5') {
        return isPl ? `Uruchamia się od poniedziałku do piątku o ${timeStr}.` : `Runs Monday through Friday at ${timeStr}.`;
      }
      if (dow === '6,0' || dow === '0,6' || dow === '6,7') {
        return isPl ? `Uruchamia się w weekendy (sobota i niedziela) o ${timeStr}.` : `Runs on weekends at ${timeStr}.`;
      }
      if (dow === '0' || dow === '7') {
        return isPl ? `Uruchamia się w każdą niedzielę o ${timeStr}.` : `Runs every Sunday at ${timeStr}.`;
      }
    }
    return isPl ? `Harmonogram: ${value}` : `Schedule: ${value}`;
  };

  return (
    <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5 space-y-3">
      {/* Nagłówek kreatora z podglądem */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-indigo-400 flex items-center gap-1.5 uppercase tracking-wider">
          <Clock className="w-3.5 h-3.5" />
          {isPl ? 'Kreator Harmonogramu' : 'Schedule Builder'}
        </span>
        <div className="flex items-center gap-1.5 font-mono text-[11px] bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
          <span className="text-slate-500">Cron:</span>
          <span className="text-indigo-300 font-bold">
            {value.trim() ? value : (isPl ? '(brak - ręczne)' : '(none - manual)')}
          </span>
        </div>
      </div>

      {/* Wybór głównego trybu częstotliwości */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5 text-xs">
        {[
          { id: 'daily', label: isPl ? 'Codziennie' : 'Daily' },
          { id: 'hourly', label: isPl ? 'Co godz.' : 'Hourly' },
          { id: 'interval', label: isPl ? 'Co X godz.' : 'Interval' },
          { id: 'weekdays', label: isPl ? 'Wybrane dni' : 'Weekdays' },
          { id: 'manual', label: isPl ? 'Ręcznie' : 'Manual' },
          { id: 'custom', label: isPl ? 'Własny' : 'Custom' },
        ].map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => handleModeChange(item.id as Mode)}
            className={`py-1.5 px-2 rounded-lg text-center font-medium transition border ${
              mode === item.id
                ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
                : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Parametry dla poszczególnych trybów */}
      <div className="pt-1">
        {mode === 'daily' && (
          <div className="flex items-center gap-3 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
            <span className="text-xs text-slate-400 font-medium">
              {isPl ? 'Godzina uruchomienia:' : 'Execution time:'}
            </span>
            <div className="flex items-center gap-1">
              <select
                value={hour}
                onChange={(e) => {
                  setHour(e.target.value);
                  updateCron('daily', e.target.value, minute, intervalHours, weekdaysPreset);
                }}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white font-mono"
              >
                {Array.from({ length: 24 }).map((_, i) => {
                  const val = String(i).padStart(2, '0');
                  return <option key={val} value={val}>{val}:00</option>;
                })}
              </select>
              <span className="text-slate-500">:</span>
              <select
                value={minute}
                onChange={(e) => {
                  setMinute(e.target.value);
                  updateCron('daily', hour, e.target.value, intervalHours, weekdaysPreset);
                }}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white font-mono"
              >
                {['00', '15', '30', '45'].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            {/* Szybkie skróty */}
            <div className="hidden sm:flex items-center gap-1.5 ml-auto text-[11px]">
              {['02:00', '03:00', '04:00'].map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => {
                    const [h, m] = t.split(':');
                    setHour(h);
                    setMinute(m);
                    updateCron('daily', h, m, intervalHours, weekdaysPreset);
                  }}
                  className="px-1.5 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-mono"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}

        {mode === 'hourly' && (
          <div className="flex items-center gap-3 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
            <span className="text-xs text-slate-400 font-medium">
              {isPl ? 'Minuta każdej godziny:' : 'Minute of every hour:'}
            </span>
            <select
              value={minute}
              onChange={(e) => {
                setMinute(e.target.value);
                updateCron('hourly', hour, e.target.value, intervalHours, weekdaysPreset);
              }}
              className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white font-mono"
            >
              {['00', '05', '10', '15', '30', '45'].map((m) => (
                <option key={m} value={m}>:{m}</option>
              ))}
            </select>
          </div>
        )}

        {mode === 'interval' && (
          <div className="flex items-center gap-3 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
            <span className="text-xs text-slate-400 font-medium">
              {isPl ? 'Uruchamiaj co:' : 'Run every:'}
            </span>
            <select
              value={intervalHours}
              onChange={(e) => {
                setIntervalHours(e.target.value);
                updateCron('interval', hour, minute, e.target.value, weekdaysPreset);
              }}
              className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white font-mono"
            >
              <option value="2">2 {isPl ? 'godziny' : 'hours'}</option>
              <option value="3">3 {isPl ? 'godziny' : 'hours'}</option>
              <option value="4">4 {isPl ? 'godziny' : 'hours'}</option>
              <option value="6">6 {isPl ? 'godzin' : 'hours'}</option>
              <option value="8">8 {isPl ? 'godzin' : 'hours'}</option>
              <option value="12">12 {isPl ? 'godzin' : 'hours'}</option>
            </select>
            <span className="text-xs text-slate-500 font-mono">
              (0 */{intervalHours} * * *)
            </span>
          </div>
        )}

        {mode === 'weekdays' && (
          <div className="space-y-2 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400 font-medium">
                {isPl ? 'Dni tygodnia:' : 'Days:'}
              </span>
              {[
                { id: '1-5', label: isPl ? 'Pon - Pt' : 'Mon - Fri' },
                { id: '6,0', label: isPl ? 'Weekend (Sob, Niedz)' : 'Weekend' },
                { id: '1', label: isPl ? 'Tylko Poniedziałki' : 'Mondays only' },
                { id: '0', label: isPl ? 'Tylko Niedziele' : 'Sundays only' },
              ].map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setWeekdaysPreset(p.id);
                    updateCron('weekdays', hour, minute, intervalHours, p.id);
                  }}
                  className={`px-2 py-1 rounded text-xs transition border ${
                    weekdaysPreset === p.id
                      ? 'bg-indigo-600/30 border-indigo-500 text-white font-semibold'
                      : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 pt-1 border-t border-slate-800/40">
              <span className="text-xs text-slate-400 font-medium">
                {isPl ? 'Godzina:' : 'Time:'}
              </span>
              <select
                value={hour}
                onChange={(e) => {
                  setHour(e.target.value);
                  updateCron('weekdays', e.target.value, minute, intervalHours, weekdaysPreset);
                }}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white font-mono"
              >
                {Array.from({ length: 24 }).map((_, i) => {
                  const val = String(i).padStart(2, '0');
                  return <option key={val} value={val}>{val}:00</option>;
                })}
              </select>
              <span className="text-slate-500">:</span>
              <select
                value={minute}
                onChange={(e) => {
                  setMinute(e.target.value);
                  updateCron('weekdays', hour, e.target.value, intervalHours, weekdaysPreset);
                }}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-white font-mono"
              >
                {['00', '15', '30', '45'].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {mode === 'manual' && (
          <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-lg">
            <Info className="w-4 h-4 flex-shrink-0" />
            <span>
              {isPl 
                ? 'Harmonogram wyłączony. Zadanie będzie uruchamiane tylko po kliknięciu przycisku "Start" w panelu.' 
                : 'Scheduler disabled. Task will only execute when you manually click "Run" in the dashboard.'}
            </span>
          </div>
        )}

        {mode === 'custom' && (
          <div className="space-y-1.5 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
            <label className="block text-xs text-slate-400 font-medium">
              {isPl ? 'Standardowy 5-polowy format Cron (min godz dzień msc dzień_tyg):' : 'Standard 5-field Cron expression:'}
            </label>
            <input
              type="text"
              value={customCron}
              onChange={(e) => {
                setCustomCron(e.target.value);
                onChange(e.target.value);
              }}
              placeholder="0 3 * * *"
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-indigo-500 transition"
            />
          </div>
        )}
      </div>

      {/* Wyjaśnienie słowne */}
      <div className="text-[11px] text-slate-400 bg-slate-900/40 px-3 py-2 rounded-lg flex items-center gap-2 border border-slate-800/30">
        <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
        <span className="font-medium">{getHumanDescription()}</span>
      </div>
    </div>
  );
}
