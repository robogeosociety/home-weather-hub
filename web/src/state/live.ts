import { create } from 'zustand';
import type { DecodedEvent, EvtStrike, ObsSt, RapidWind, SnapshotResponse } from '../api/types';

interface LiveState {
  obsSt: ObsSt | null;
  rapidWind: RapidWind | null;
  recentStrikes: EvtStrike[];
  lastObsStAt: number | null; // monotonic ms — for stale detection
  lastRapidWindAt: number | null;
  applySnapshot: (snap: SnapshotResponse) => void;
  applyEvent: (event: DecodedEvent) => void;
  clearStrike: (timeEpoch: number) => void;
}

const STRIKE_WINDOW_MS = 30 * 60 * 1000; // strikes stay on the map 30 min

export const useLive = create<LiveState>((set) => ({
  obsSt: null,
  rapidWind: null,
  recentStrikes: [],
  lastObsStAt: null,
  lastRapidWindAt: null,
  applySnapshot: (snap) =>
    set(() => ({
      obsSt: snap.events.obs_st ?? null,
      rapidWind: snap.events.rapid_wind ?? null,
      lastObsStAt: snap.events.obs_st ? performance.now() : null,
      lastRapidWindAt: snap.events.rapid_wind ? performance.now() : null,
    })),
  applyEvent: (event) =>
    set((s) => {
      const now = performance.now();
      switch (event.type) {
        case 'obs_st':
          return { obsSt: event, lastObsStAt: now };
        case 'rapid_wind':
          return { rapidWind: event, lastRapidWindAt: now };
        case 'evt_strike': {
          const cutoff = Date.now() / 1000 - STRIKE_WINDOW_MS / 1000;
          const fresh = s.recentStrikes.filter((s) => (s.time_epoch ?? 0) > cutoff);
          return { recentStrikes: [...fresh, event] };
        }
        default:
          return s;
      }
    }),
  clearStrike: (timeEpoch) =>
    set((s) => ({
      recentStrikes: s.recentStrikes.filter((x) => x.time_epoch !== timeEpoch),
    })),
}));

export type WidgetState = 'loading' | 'empty' | 'stale' | 'live';

export function obsStState(lastAt: number | null): WidgetState {
  if (lastAt === null) return 'empty';
  const ageSec = (performance.now() - lastAt) / 1000;
  if (ageSec > 120) return 'stale';
  return 'live';
}

export function rapidWindState(lastAt: number | null): WidgetState {
  if (lastAt === null) return 'empty';
  const ageSec = (performance.now() - lastAt) / 1000;
  if (ageSec > 6) return 'stale';
  return 'live';
}
