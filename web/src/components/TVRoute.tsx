import { useLive } from '../state/live';

/**
 * Phase 1 placeholder for the ?tv=1 kiosk mode.
 *
 * Phase 2 will replace this with a full Local-on-the-8s scene script —
 * AnimatePresence-driven slide cycle, smooth-jazz audio toggle, the works.
 */
export function TVRoute() {
  const obs = useLive((s) => s.obsSt);
  const temp = obs?.air_temp_f;

  return (
    <div className="twc-tv">
      <div className="twc-tv-eyebrow">CURRENT CONDITIONS</div>
      <div className="twc-tv-headline">SEATTLE</div>
      <div className="twc-tv-temp">{temp != null ? Math.round(temp) : '—'}°</div>
      <div className="twc-tv-footnote">
        TV mode (Phase 2 will animate the full Local Forecast scene cycle)
      </div>
    </div>
  );
}
