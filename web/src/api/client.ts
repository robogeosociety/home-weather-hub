import type {
  HistoryResponse,
  MetricKey,
  SavedLayouts,
  SnapshotResponse,
  StationConfig,
  StrikesResponse,
} from './types';

const base = '';

export async function fetchSnapshot(): Promise<SnapshotResponse> {
  const r = await fetch(`${base}/api/snapshot`);
  if (!r.ok) throw new Error(`snapshot ${r.status}`);
  return r.json();
}

export async function fetchHistory(metric: MetricKey, hours = 24): Promise<HistoryResponse> {
  const since = new Date(Date.now() - hours * 3600 * 1000).toISOString();
  const r = await fetch(`${base}/api/history?metric=${encodeURIComponent(metric)}&since=${since}`);
  if (!r.ok) throw new Error(`history ${r.status}`);
  return r.json();
}

export async function fetchStrikes(hours = 6): Promise<StrikesResponse> {
  const since = new Date(Date.now() - hours * 3600 * 1000).toISOString();
  const r = await fetch(`${base}/api/strikes?since=${since}`);
  if (!r.ok) throw new Error(`strikes ${r.status}`);
  return r.json();
}

export async function fetchStation(): Promise<StationConfig> {
  const r = await fetch(`${base}/api/station`);
  if (!r.ok) throw new Error(`station ${r.status}`);
  return r.json();
}

export async function fetchLayout(): Promise<Partial<SavedLayouts>> {
  const r = await fetch(`${base}/api/layout`);
  if (!r.ok) throw new Error(`layout ${r.status}`);
  return r.json();
}

export async function putLayout(layout: SavedLayouts): Promise<void> {
  const r = await fetch(`${base}/api/layout`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(layout),
  });
  if (!r.ok) throw new Error(`putLayout ${r.status}`);
}

export async function triggerSyntheticStrike(distance_km?: number): Promise<void> {
  const url = distance_km
    ? `${base}/api/_dev/strike?distance_km=${distance_km}`
    : `${base}/api/_dev/strike`;
  await fetch(url, { method: 'POST' });
}

// ----- WebSocket -----

export type WSMessage =
  | { type: 'snapshot'; data: SnapshotResponse }
  | { type: 'event'; data: { type: string } & Record<string, unknown> };

export function openLiveSocket(onMessage: (msg: WSMessage) => void): () => void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws`;
  let ws: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let closed = false;

  const connect = () => {
    ws = new WebSocket(url);
    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      if (closed) return;
      reconnectTimer = window.setTimeout(connect, 1500);
    };
    ws.onerror = () => ws?.close();
  };

  connect();

  return () => {
    closed = true;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    ws?.close();
  };
}
