import { useEffect, useState } from 'react';
import { useSettings } from '../state/settings';
import { triggerSyntheticStrike } from '../api/client';

function useNowText() {
  const [text, setText] = useState(formatNow());
  useEffect(() => {
    const t = setInterval(() => setText(formatNow()), 1000);
    return () => clearInterval(t);
  }, []);
  return text;
}

function formatNow(): string {
  return new Date().toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function Toolbar() {
  const theme = useSettings((s) => s.theme);
  const toggleTheme = useSettings((s) => s.toggleTheme);
  const editMode = useSettings((s) => s.editMode);
  const setEditMode = useSettings((s) => s.setEditMode);
  const now = useNowText();

  return (
    <div className="twc-toolbar">
      <div className="twc-brand">
        <div className="twc-brand-mark">HOME WEATHER HUB</div>
        <div className="twc-brand-sub">live local conditions</div>
      </div>

      <div className="twc-toolbar-spacer" />

      <div className="twc-clock">{now}</div>

      <button
        type="button"
        className="twc-btn"
        data-active={editMode}
        onClick={() => setEditMode(!editMode)}
        title="Toggle widget layout edit mode"
      >
        {editMode ? '◇ DONE' : '◇ LAYOUT'}
      </button>

      {editMode && (
        <button
          type="button"
          className="twc-btn"
          onClick={() => triggerSyntheticStrike()}
          title="Trigger synthetic lightning strike (dev)"
        >
          ⚡ TEST STRIKE
        </button>
      )}

      <button
        type="button"
        className="twc-btn"
        onClick={toggleTheme}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        aria-label="toggle theme"
      >
        {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
      </button>
    </div>
  );
}

function SunIcon() {
  return (
    <svg className="twc-btn-icon" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="4.5" fill="currentColor" />
      {Array.from({ length: 8 }, (_, i) => {
        const a = (i * Math.PI) / 4;
        const x1 = 12 + Math.cos(a) * 7;
        const y1 = 12 + Math.sin(a) * 7;
        const x2 = 12 + Math.cos(a) * 9.5;
        const y2 = 12 + Math.sin(a) * 9.5;
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth="2" strokeLinecap="round" />;
      })}
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg className="twc-btn-icon" viewBox="0 0 24 24" fill="none">
      <path
        d="M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z"
        fill="currentColor"
      />
    </svg>
  );
}
