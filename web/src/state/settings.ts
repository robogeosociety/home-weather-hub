import { create } from 'zustand';

type Theme = 'dark' | 'light';

interface SettingsState {
  theme: Theme;
  editMode: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setEditMode: (b: boolean) => void;
}

function initialTheme(): Theme {
  const params = new URLSearchParams(location.search);
  const param = params.get('darkmode');
  if (param === 'true') return 'dark';
  if (param === 'false') return 'light';
  const saved = localStorage.getItem('twc.theme') as Theme | null;
  return saved === 'light' ? 'light' : 'dark';
}

export const useSettings = create<SettingsState>((set, get) => ({
  theme: initialTheme(),
  editMode: false,
  setTheme: (t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('twc.theme', t);
    set({ theme: t });
  },
  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
  setEditMode: (b) => set({ editMode: b }),
}));

// Apply initial theme to <html> immediately on import.
document.documentElement.dataset.theme = useSettings.getState().theme;
