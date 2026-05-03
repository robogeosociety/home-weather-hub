import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { fetchHistory } from '../../api/client';
import type { MetricKey, WidgetConfig } from '../../api/types';
import { useLive } from '../../state/live';
import { useSettings } from '../../state/settings';
import { BigReadout } from '../BigReadout';
import { MetricGraph } from '../MetricGraph';
import { TVChrome } from '../TVChrome';
import { useLayout } from '../../state/layout';

interface MetricSpec {
  title: string;
  unit: string;
  digits: number;
  toneFn?: (v: number) => 'cool' | 'warm' | 'hot' | 'default';
  color: string;
  secondary?: (live: ReturnType<typeof useLive.getState>) => string | undefined;
}

const SPECS: Record<MetricKey, MetricSpec> = {
  'outdoor.air_temp_f': {
    title: 'OUTSIDE TEMP',
    unit: '°F',
    digits: 0,
    color: '#FFD600',
    toneFn: (v) => (v >= 85 ? 'hot' : v >= 68 ? 'warm' : v <= 40 ? 'cool' : 'default'),
    secondary: (live) => {
      const c = live.obsSt?.air_temp_c;
      return c != null ? `${c.toFixed(1)} °C` : undefined;
    },
  },
  'outdoor.air_temp_c': { title: 'OUTSIDE TEMP', unit: '°C', digits: 1, color: '#FFD600' },
  'outdoor.relative_humidity_pct': {
    title: 'HUMIDITY',
    unit: '%',
    digits: 0,
    color: '#00D4FF',
  },
  'outdoor.pressure_mb': {
    title: 'PRESSURE',
    unit: 'mb',
    digits: 0,
    color: '#00D4FF',
    secondary: (live) => {
      const mb = live.obsSt?.pressure_mb;
      return mb != null ? `${(mb * 0.02953).toFixed(2)} inHg` : undefined;
    },
  },
  'outdoor.wind_avg_mph': {
    title: 'WIND',
    unit: 'mph',
    digits: 1,
    color: '#FFD600',
  },
  'outdoor.wind_gust_mph': { title: 'WIND GUST', unit: 'mph', digits: 1, color: '#FF8C00' },
  'outdoor.wind_direction_deg': { title: 'WIND DIR', unit: '°', digits: 0, color: '#00D4FF' },
  'outdoor.uv_index': {
    title: 'UV INDEX',
    unit: '',
    digits: 1,
    color: '#FF8C00',
    toneFn: (v) => (v >= 8 ? 'hot' : v >= 6 ? 'warm' : 'default'),
  },
  'outdoor.illuminance_lux': { title: 'LUX', unit: '', digits: 0, color: '#FFD600' },
  'outdoor.solar_radiation_w_m2': { title: 'SOLAR', unit: 'W/m²', digits: 0, color: '#FFD600' },
  'outdoor.rain_accumulated_in': {
    title: 'RAIN',
    unit: 'in/min',
    digits: 3,
    color: '#00D4FF',
  },
  'outdoor.battery_voltage': { title: 'BATTERY', unit: 'V', digits: 2, color: '#00D4FF' },
  'outdoor.rapid_wind_speed_mph': { title: 'WIND (LIVE)', unit: 'mph', digits: 1, color: '#FFD600' },
  'outdoor.rapid_wind_direction_deg': {
    title: 'WIND DIR (LIVE)',
    unit: '°',
    digits: 0,
    color: '#00D4FF',
  },
};

interface MetricWidgetProps {
  config: WidgetConfig;
}

function selectStat(points: { v: number }[], stat: WidgetConfig['stat']): number | null {
  if (points.length === 0) return null;
  const vs = points.map((p) => p.v);
  switch (stat) {
    case 'min':
      return Math.min(...vs);
    case 'max':
      return Math.max(...vs);
    case 'mean':
      return vs.reduce((a, b) => a + b, 0) / vs.length;
    case 'current':
    default:
      return vs[vs.length - 1];
  }
}

export function MetricWidget({ config }: MetricWidgetProps) {
  const live = useLive();
  const editMode = useSettings((s) => s.editMode);
  const updateWidget = useLayout((s) => s.updateWidget);
  const [forceTick, setForceTick] = useState(0);
  const spec = SPECS[config.metric];

  // Re-render every 5s so stale-state indicators update without new data.
  useEffect(() => {
    const t = setInterval(() => setForceTick((x) => x + 1), 5000);
    return () => clearInterval(t);
  }, []);

  const historyQ = useQuery({
    queryKey: ['history', config.metric, config.stat, config.display],
    queryFn: () => fetchHistory(config.metric, 24),
    enabled: config.display === 'graph' || config.stat !== 'current',
    refetchInterval: 60_000,
  });

  const liveValue = live.obsSt?.[mapMetricToObsStField(config.metric)] as number | null | undefined;
  const stat = config.stat ?? 'current';

  const value = useMemo(() => {
    if (stat === 'current') return liveValue;
    if (!historyQ.data) return null;
    return selectStat(historyQ.data.points, stat);
  }, [stat, liveValue, historyQ.data, forceTick]);

  const widgetState = computeWidgetState(live.lastObsStAt, value);
  const tone = value != null && spec.toneFn ? spec.toneFn(value) : 'default';

  return (
    <TVChrome
      title={spec.title}
      stat={stat}
      state={widgetState}
      display={config.display}
      onDisplayChange={(d) => updateWidget(config.i, { display: d })}
      showDisplayToggle={editMode}
    >
      {config.display === 'graph' ? (
        <MetricGraph points={historyQ.data?.points ?? []} color={spec.color} unit={spec.unit} />
      ) : (
        <BigReadout
          value={value ?? null}
          unit={spec.unit}
          digits={spec.digits}
          tone={tone}
          secondary={stat === 'current' && spec.secondary ? spec.secondary(live) : undefined}
        />
      )}
      {editMode && <StatChooser config={config} />}
    </TVChrome>
  );
}

function StatChooser({ config }: { config: WidgetConfig }) {
  const updateWidget = useLayout((s) => s.updateWidget);
  const stats: WidgetConfig['stat'][] = ['current', 'min', 'max', 'mean'];
  return (
    <div
      onMouseDown={(e) => e.stopPropagation()}
      style={{
        position: 'absolute',
        bottom: 6,
        left: 6,
        right: 6,
        display: 'flex',
        gap: 4,
        justifyContent: 'center',
      }}
    >
      {stats.map((s) => (
        <button
          key={s}
          type="button"
          className="twc-btn"
          data-active={config.stat === s}
          style={{ fontSize: 9, padding: '2px 6px', letterSpacing: '0.16em' }}
          onClick={() => updateWidget(config.i, { stat: s })}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

function mapMetricToObsStField(
  metric: MetricKey,
): keyof NonNullable<ReturnType<typeof useLive.getState>['obsSt']> {
  // The metric key encodes both event type and field; for current value lookup
  // on obs_st-backed metrics, strip the prefix.
  const trailing = metric.split('.').slice(1).join('.');
  // rapid_wind metrics aren't on obs_st — caller falls back to live.rapidWind separately.
  if (trailing.startsWith('rapid_wind_')) {
    return trailing as never;
  }
  return trailing as never;
}

function computeWidgetState(
  lastAt: number | null,
  value: number | null | undefined,
): 'loading' | 'empty' | 'stale' | 'live' {
  if (lastAt === null && (value === null || value === undefined)) return 'empty';
  if (lastAt === null) return 'loading';
  const ageSec = (performance.now() - lastAt) / 1000;
  if (ageSec > 120) return 'stale';
  return 'live';
}
