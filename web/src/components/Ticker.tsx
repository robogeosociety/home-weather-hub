import { useLive } from '../state/live';

export function Ticker() {
  const obs = useLive((s) => s.obsSt);

  const items: Array<[string, string]> = [
    ['TEMP', obs?.air_temp_f != null ? `${Math.round(obs.air_temp_f)}°F` : '—'],
    ['HUMIDITY', obs?.relative_humidity_pct != null ? `${Math.round(obs.relative_humidity_pct)}%` : '—'],
    ['WIND', obs?.wind_avg_mph != null ? `${obs.wind_avg_mph.toFixed(1)} MPH` : '—'],
    ['GUST', obs?.wind_gust_mph != null ? `${obs.wind_gust_mph.toFixed(1)} MPH` : '—'],
    ['PRESSURE', obs?.pressure_mb != null ? `${Math.round(obs.pressure_mb)} mb` : '—'],
    ['UV', obs?.uv_index != null ? obs.uv_index.toFixed(1) : '—'],
    ['RAIN', obs?.rain_accumulated_in != null ? `${obs.rain_accumulated_in.toFixed(3)} IN/MIN` : '—'],
  ];

  // Duplicate the items so the marquee loops seamlessly.
  const doubled = [...items, ...items];

  return (
    <div className="twc-ticker">
      <div className="twc-ticker-label">LOCAL ON THE 8s</div>
      <div className="twc-ticker-track">
        <div className="twc-ticker-content">
          {doubled.map(([label, value], i) => (
            <div key={i} className="twc-ticker-item">
              {label} <span>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
