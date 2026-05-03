import { useEffect, useState } from 'react';
import { Circle, MapContainer, TileLayer } from 'react-leaflet';
import type { EvtStrike, StationConfig } from '../api/types';
import { fetchStation } from '../api/client';

interface StrikeMapProps {
  strikes: EvtStrike[];
}

const FALLBACK_LAT = 47.6062;  // Seattle (Mac Mini home base)
const FALLBACK_LNG = -122.3321;

export function StrikeMap({ strikes }: StrikeMapProps) {
  const [station, setStation] = useState<StationConfig | null>(null);

  useEffect(() => {
    fetchStation().then(setStation).catch(() => {
      setStation({ lat: null, lng: null, name: 'Tempest Station', metric_keys: [] });
    });
  }, []);

  if (!station) {
    return <div className="twc-empty-msg">acquiring station…</div>;
  }

  const lat = station.lat ?? FALLBACK_LAT;
  const lng = station.lng ?? FALLBACK_LNG;
  const usingFallback = station.lat == null || station.lng == null;

  // Fit bounds to the largest strike distance + padding.
  const maxKm = Math.max(20, ...strikes.map((s) => s.distance_km ?? 0));
  const zoom = maxKm > 60 ? 7 : maxKm > 30 ? 8 : 9;

  return (
    <div className="twc-map">
      <div className="twc-map-overlay-info">
        {strikes.length > 0
          ? `${strikes.length} strike${strikes.length === 1 ? '' : 's'} · last ${maxKm.toFixed(1)} km`
          : 'no strikes'}
        {usingFallback && ' · fallback location'}
      </div>
      <MapContainer
        center={[lat, lng]}
        zoom={zoom}
        scrollWheelZoom={false}
        zoomControl={false}
        attributionControl={false}
        style={{ width: '100%', height: '100%' }}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains={['a', 'b', 'c', 'd']}
          maxZoom={19}
        />
        {/* Station marker — small yellow disc with cyan halo */}
        <Circle
          center={[lat, lng]}
          radius={400}
          pathOptions={{
            color: '#FFD600',
            weight: 2,
            fillColor: '#FFD600',
            fillOpacity: 0.85,
          }}
        />
        <Circle
          center={[lat, lng]}
          radius={1500}
          pathOptions={{
            color: '#00D4FF',
            weight: 1,
            fillOpacity: 0,
            opacity: 0.6,
            dashArray: '4 4',
          }}
        />
        {strikes.map((s, i) => (
          <Circle
            key={`${s.time_epoch ?? 'k'}-${i}`}
            center={[lat, lng]}
            radius={(s.distance_km ?? 0) * 1000}
            className="twc-strike-ring"
            pathOptions={{
              color: '#FF2188',
              weight: 4,
              fillOpacity: 0,
              opacity: 0.95,
            }}
          />
        ))}
      </MapContainer>
    </div>
  );
}
