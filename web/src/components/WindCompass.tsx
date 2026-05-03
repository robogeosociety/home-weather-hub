interface WindCompassProps {
  speedMph: number | null | undefined;
  directionDeg: number | null | undefined;
  gustMph?: number | null;
}

const CARDS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

function degToCard(deg: number): string {
  return CARDS[Math.round(((deg % 360) / 45)) % 8];
}

export function WindCompass({ speedMph, directionDeg, gustMph }: WindCompassProps) {
  const dir = directionDeg ?? 0;
  const speed = speedMph ?? 0;
  const cx = 200;
  const cy = 200;
  const r = 150;

  // Eight cardinal tick marks; the "active" card is highlighted.
  const ticks = Array.from({ length: 36 }, (_, i) => {
    const angle = (i * 10 - 90) * (Math.PI / 180);
    const inner = i % 9 === 0 ? r - 22 : r - 10;
    const x1 = cx + Math.cos(angle) * (r - 4);
    const y1 = cy + Math.sin(angle) * (r - 4);
    const x2 = cx + Math.cos(angle) * inner;
    const y2 = cy + Math.sin(angle) * inner;
    return (
      <line
        key={i}
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke="var(--twc-cyan-dim)"
        strokeWidth={i % 9 === 0 ? 2 : 1}
        opacity={i % 9 === 0 ? 0.9 : 0.45}
      />
    );
  });

  const cardLabels = CARDS.map((c, i) => {
    const angle = (i * 45 - 90) * (Math.PI / 180);
    const x = cx + Math.cos(angle) * (r - 38);
    const y = cy + Math.sin(angle) * (r - 38) + 5;
    return (
      <text
        key={c}
        x={x}
        y={y}
        textAnchor="middle"
        fontFamily="Big Shoulders Display, sans-serif"
        fontWeight={c === 'N' ? 900 : 700}
        fontSize={c === 'N' ? 22 : 16}
        letterSpacing="0.2em"
        fill={c === 'N' ? 'var(--twc-yellow)' : 'var(--twc-bone-dim)'}
        opacity={c === 'N' ? 1 : 0.65}
        style={c === 'N' ? { filter: 'drop-shadow(0 0 6px var(--twc-yellow))' } : undefined}
      >
        {c}
      </text>
    );
  });

  // Arrow rotates to the wind direction (FROM convention).
  const arrowAngle = dir;

  return (
    <div className="twc-compass">
      <svg className="twc-compass-svg" viewBox="0 0 400 400">
        <defs>
          <radialGradient id="compass-bg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(0,0,0,0.6)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0.05)" />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cy} r={r} fill="url(#compass-bg)" stroke="var(--twc-cyan)" strokeWidth={1} opacity={0.6} />
        <circle cx={cx} cy={cy} r={r - 20} fill="none" stroke="var(--twc-cyan-dim)" strokeWidth={0.5} opacity={0.5} />
        {ticks}
        {cardLabels}

        <g transform={`rotate(${arrowAngle} ${cx} ${cy})`}>
          <polygon
            points={`${cx},${cy - r + 12} ${cx - 14},${cy} ${cx},${cy - 22} ${cx + 14},${cy}`}
            fill="var(--twc-yellow)"
            stroke="var(--twc-bezel)"
            strokeWidth={1.5}
            style={{ filter: 'drop-shadow(0 0 8px var(--twc-yellow))' }}
          />
        </g>
        <circle cx={cx} cy={cy} r={6} fill="var(--twc-yellow)" />
      </svg>
      <div className="twc-compass-readout">
        <div className="twc-compass-speed">
          {speedMph === null || speedMph === undefined ? '—' : speed.toFixed(1)}
        </div>
        <div className="twc-compass-card">{degToCard(dir)} · {Math.round(dir)}°</div>
        {gustMph != null && gustMph > 0 && (
          <div className="twc-readout-secondary" style={{ marginTop: 12 }}>
            GUST {gustMph.toFixed(1)} MPH
          </div>
        )}
      </div>
    </div>
  );
}
