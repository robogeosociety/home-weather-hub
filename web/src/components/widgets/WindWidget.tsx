import { useEffect, useState } from 'react';
import type { WidgetConfig } from '../../api/types';
import { useLive } from '../../state/live';
import { useSettings } from '../../state/settings';
import { TVChrome } from '../TVChrome';
import { WindCompass } from '../WindCompass';
import { useLayout } from '../../state/layout';

interface WindWidgetProps {
  config: WidgetConfig;
}

export function WindWidget({ config }: WindWidgetProps) {
  const live = useLive();
  const editMode = useSettings((s) => s.editMode);
  const updateWidget = useLayout((s) => s.updateWidget);
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 3000);
    return () => clearInterval(t);
  }, []);

  // Prefer rapid_wind for live direction; fall back to obs_st averages.
  const speed = live.rapidWind?.wind_speed_mph ?? live.obsSt?.wind_avg_mph ?? null;
  const dir = live.rapidWind?.wind_direction_deg ?? live.obsSt?.wind_direction_deg ?? null;
  const gust = live.obsSt?.wind_gust_mph ?? null;

  const lastAt = live.lastRapidWindAt ?? live.lastObsStAt;
  const widgetState =
    lastAt === null
      ? 'empty'
      : (performance.now() - lastAt) / 1000 > 120
        ? 'stale'
        : 'live';

  return (
    <TVChrome
      title="WIND"
      state={widgetState}
      display={config.display}
      onDisplayChange={(d) => updateWidget(config.i, { display: d })}
      showDisplayToggle={editMode}
    >
      <WindCompass speedMph={speed} directionDeg={dir} gustMph={gust} />
    </TVChrome>
  );
}
