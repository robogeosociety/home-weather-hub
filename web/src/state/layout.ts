import { create } from 'zustand';
import type { Breakpoint, LayoutItem, SavedLayouts, WidgetConfig } from '../api/types';
import { fetchLayout, putLayout } from '../api/client';

// The palette is the master list of every widget the dashboard knows how to
// render. `widgets` (in store state) is the subset currently on the canvas;
// anything in the palette but not in `widgets` shows up as an inactive pill
// the user can click to re-enable.
export const WIDGET_PALETTE: ReadonlyArray<WidgetConfig & { label: string }> = [
  { i: 'temp', label: 'Temp', metric: 'outdoor.air_temp_f', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'wind', label: 'Wind', metric: 'outdoor.wind_avg_mph', display: 'big-number', stat: 'current', kind: 'wind' },
  { i: 'humidity', label: 'Humidity', metric: 'outdoor.relative_humidity_pct', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'pressure', label: 'Pressure', metric: 'outdoor.pressure_mb', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'uv', label: 'UV', metric: 'outdoor.uv_index', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'rain', label: 'Rain', metric: 'outdoor.rain_accumulated_in', display: 'big-number', stat: 'current', kind: 'metric' },
  { i: 'strikes', label: 'Lightning', metric: 'outdoor.air_temp_f', display: 'big-number', stat: 'current', kind: 'strikes' },
];

const DEFAULT_WIDGETS: WidgetConfig[] = WIDGET_PALETTE.map(({ label: _label, ...w }) => w);

// Default size when re-adding a widget the user previously removed. Picked to
// fit comfortably in any breakpoint without compaction surprises.
const DEFAULT_ITEM_SIZE: Record<Breakpoint, { w: number; h: number; minW: number; minH: number }> = {
  tv: { w: 3, h: 4, minW: 2, minH: 3 },
  mac: { w: 3, h: 4, minW: 2, minH: 3 },
  tablet: { w: 3, h: 4, minW: 2, minH: 3 },
  phone: { w: 1, h: 4, minW: 1, minH: 3 },
};

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
  removeWidget: (i: string) => void;
  addWidget: (i: string) => void;
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
  removeWidget: (i) => {
    set((s) => ({
      widgets: s.widgets.filter((w) => w.i !== i),
      layouts: Object.fromEntries(
        Object.entries(s.layouts).map(([bp, items]) => [bp, items.filter((it) => it.i !== i)]),
      ) as Record<Breakpoint, LayoutItem[]>,
    }));
    void get().persist();
  },
  addWidget: (i) => {
    set((s) => {
      if (s.widgets.some((w) => w.i === i)) return s;
      const palette = WIDGET_PALETTE.find((p) => p.i === i);
      if (!palette) return s;
      const { label: _label, ...config } = palette;
      // For each breakpoint, drop the new tile at the bottom of the column so
      // RGL's vertical compaction tucks it into the first available slot.
      const layouts = Object.fromEntries(
        (Object.entries(s.layouts) as [Breakpoint, LayoutItem[]][]).map(([bp, items]) => {
          const maxY = items.reduce((m, it) => Math.max(m, it.y + it.h), 0);
          const size = DEFAULT_ITEM_SIZE[bp];
          return [bp, [...items, { i, x: 0, y: maxY, ...size }]];
        }),
      ) as Record<Breakpoint, LayoutItem[]>;
      return { widgets: [...s.widgets, config], layouts };
    });
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
