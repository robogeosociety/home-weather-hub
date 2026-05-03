import { create } from 'zustand';
import type { Breakpoint, LayoutItem, SavedLayouts, WidgetConfig } from '../api/types';
import { fetchLayout, putLayout } from '../api/client';

const DEFAULT_WIDGETS: WidgetConfig[] = [
  { i: 'temp', metric: 'outdoor.air_temp_f', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'wind', metric: 'outdoor.wind_avg_mph', display: 'big-number', stat: 'current', kind: 'wind' },
  { i: 'humidity', metric: 'outdoor.relative_humidity_pct', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'pressure', metric: 'outdoor.pressure_mb', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'uv', metric: 'outdoor.uv_index', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'rain', metric: 'outdoor.rain_accumulated_in', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'strikes', metric: 'outdoor.air_temp_f', display: 'big-number', stat: 'current', kind: 'strikes' },
];

const DEFAULT_LAYOUTS: Record<Breakpoint, LayoutItem[]> = {
  tv: [
    { i: 'temp', x: 0, y: 0, w: 5, h: 6, minW: 3, minH: 4 },
    { i: 'wind', x: 5, y: 0, w: 4, h: 6, minW: 3, minH: 4 },
    { i: 'strikes', x: 9, y: 0, w: 3, h: 6, minW: 3, minH: 4 },
    { i: 'humidity', x: 0, y: 6, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'pressure', x: 3, y: 6, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'uv', x: 6, y: 6, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'rain', x: 9, y: 6, w: 3, h: 4, minW: 2, minH: 3 },
  ],
  mac: [
    { i: 'temp', x: 0, y: 0, w: 4, h: 6, minW: 3, minH: 4 },
    { i: 'wind', x: 4, y: 0, w: 3, h: 6, minW: 3, minH: 4 },
    { i: 'strikes', x: 7, y: 0, w: 3, h: 6, minW: 3, minH: 4 },
    { i: 'humidity', x: 0, y: 6, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'pressure', x: 3, y: 6, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'uv', x: 6, y: 6, w: 2, h: 4, minW: 2, minH: 3 },
    { i: 'rain', x: 8, y: 6, w: 2, h: 4, minW: 2, minH: 3 },
  ],
  tablet: [
    { i: 'temp', x: 0, y: 0, w: 6, h: 5, minW: 3, minH: 4 },
    { i: 'wind', x: 0, y: 5, w: 3, h: 5, minW: 3, minH: 4 },
    { i: 'strikes', x: 3, y: 5, w: 3, h: 5, minW: 3, minH: 4 },
    { i: 'humidity', x: 0, y: 10, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'pressure', x: 3, y: 10, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'uv', x: 0, y: 14, w: 3, h: 4, minW: 2, minH: 3 },
    { i: 'rain', x: 3, y: 14, w: 3, h: 4, minW: 2, minH: 3 },
  ],
  phone: [
    { i: 'temp', x: 0, y: 0, w: 2, h: 5, minW: 2, minH: 4 },
    { i: 'wind', x: 0, y: 5, w: 2, h: 5, minW: 2, minH: 4 },
    { i: 'humidity', x: 0, y: 10, w: 1, h: 4, minW: 1, minH: 3 },
    { i: 'pressure', x: 1, y: 10, w: 1, h: 4, minW: 1, minH: 3 },
    { i: 'uv', x: 0, y: 14, w: 1, h: 4, minW: 1, minH: 3 },
    { i: 'rain', x: 1, y: 14, w: 1, h: 4, minW: 1, minH: 3 },
    { i: 'strikes', x: 0, y: 18, w: 2, h: 5, minW: 2, minH: 4 },
  ],
};

interface LayoutState {
  widgets: WidgetConfig[];
  layouts: Record<Breakpoint, LayoutItem[]>;
  loaded: boolean;
  load: () => Promise<void>;
  setLayoutForBreakpoint: (bp: Breakpoint, items: LayoutItem[]) => void;
  updateWidget: (i: string, patch: Partial<WidgetConfig>) => void;
  persist: () => Promise<void>;
}

export const useLayout = create<LayoutState>((set, get) => ({
  widgets: DEFAULT_WIDGETS,
  layouts: DEFAULT_LAYOUTS,
  loaded: false,
  load: async () => {
    try {
      const saved = await fetchLayout();
      if (saved && (saved as SavedLayouts).widgets) {
        const s = saved as SavedLayouts;
        set({ widgets: s.widgets, layouts: { ...DEFAULT_LAYOUTS, ...s.layouts }, loaded: true });
      } else {
        set({ loaded: true });
      }
    } catch {
      set({ loaded: true });
    }
  },
  setLayoutForBreakpoint: (bp, items) => {
    set((s) => ({ layouts: { ...s.layouts, [bp]: items } }));
    void get().persist();
  },
  updateWidget: (i, patch) => {
    set((s) => ({ widgets: s.widgets.map((w) => (w.i === i ? { ...w, ...patch } : w)) }));
    void get().persist();
  },
  persist: async () => {
    const s = get();
    try {
      await putLayout({ widgets: s.widgets, layouts: s.layouts });
    } catch {
      /* best-effort */
    }
  },
}));
