import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { fetchStrikes, triggerSyntheticStrike } from '../../api/client';
import { useLive } from '../../state/live';
import { useSettings } from '../../state/settings';
import { StrikeMap } from '../StrikeMap';
import { TVChrome } from '../TVChrome';
import type { EvtStrike, WidgetConfig } from '../../api/types';

interface StrikesWidgetProps {
  config: WidgetConfig;
}

export function StrikesWidget({ config: _config }: StrikesWidgetProps) {
  const live = useLive();
  const editMode = useSettings((s) => s.editMode);

  // On mount, hydrate with recent strikes from the API so we don't rely on the
  // WS being open since boot.
  const strikesQ = useQuery({
    queryKey: ['strikes'],
    queryFn: () => fetchStrikes(6),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (strikesQ.data?.strikes) {
      // We don't push these into useLive since they may already be there;
      // StrikeMap reads from the merged set computed below.
    }
  }, [strikesQ.data]);

  const strikes: EvtStrike[] = useMemo(() => {
    const fromApi: EvtStrike[] = (strikesQ.data?.strikes ?? []).map((s) => ({
      type: 'evt_strike',
      time_epoch: s.t,
      distance_km: s.distance_km,
      distance_mi: s.distance_km * 0.621371,
      energy: s.energy,
    }));
    // Merge with WS-pushed strikes; dedupe on time_epoch.
    const seen = new Set<number>();
    const all = [...fromApi, ...live.recentStrikes];
    return all.filter((s) => {
      const key = s.time_epoch ?? Math.random();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [strikesQ.data, live.recentStrikes]);

  const state =
    strikes.length === 0
      ? live.lastObsStAt
        ? 'live' // we have outdoor data but no strikes — that's fine, not "empty"
        : 'empty'
      : 'live';

  return (
    <TVChrome title="LIGHTNING" state={state}>
      {strikes.length === 0 ? (
        <div className="twc-map">
          <div className="twc-map-empty">
            <div className="twc-map-empty-glyph">all clear</div>
            <div>no strikes detected</div>
            {editMode && (
              <button
                type="button"
                className="twc-btn"
                style={{ marginTop: 16 }}
                onClick={() => triggerSyntheticStrike()}
                onMouseDown={(e) => e.stopPropagation()}
              >
                Trigger Test Strike
              </button>
            )}
          </div>
        </div>
      ) : (
        <StrikeMap strikes={strikes} />
      )}
    </TVChrome>
  );
}
