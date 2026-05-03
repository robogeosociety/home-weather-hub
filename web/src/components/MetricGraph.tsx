import { useEffect, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import type { HistoryPoint } from '../api/types';

interface MetricGraphProps {
  points: HistoryPoint[];
  color?: string;
  unit?: string;
}

export function MetricGraph({ points, color = '#FFD600', unit = '' }: MetricGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const plotRef = useRef<uPlot | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const xs = points.map((p) => p.t);
    const ys = points.map((p) => p.v);
    const data: uPlot.AlignedData = [xs, ys];

    const opts: uPlot.Options = {
      width: el.clientWidth || 240,
      height: el.clientHeight || 120,
      pxAlign: 1,
      cursor: { show: false },
      legend: { show: false },
      scales: { x: { time: true }, y: { auto: true } },
      axes: [
        {
          stroke: 'rgba(242,241,232,0.45)',
          grid: { stroke: 'rgba(0,212,255,0.08)', width: 1 },
          ticks: { stroke: 'rgba(0,212,255,0.18)' },
          font: '10px IBM Plex Mono, monospace',
        },
        {
          stroke: 'rgba(242,241,232,0.45)',
          grid: { stroke: 'rgba(0,212,255,0.08)', width: 1 },
          ticks: { stroke: 'rgba(0,212,255,0.18)' },
          font: '10px IBM Plex Mono, monospace',
          values: (_u, vals) => vals.map((v) => `${v}${unit}`),
        },
      ],
      series: [
        {},
        {
          stroke: color,
          width: 2,
          fill: `${color}33`,
          points: { show: false },
        },
      ],
    };

    plotRef.current?.destroy();
    plotRef.current = new uPlot(opts, data, el);

    const ro = new ResizeObserver(() => {
      if (plotRef.current && el) {
        plotRef.current.setSize({ width: el.clientWidth, height: el.clientHeight });
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, [points, color, unit]);

  if (points.length < 2) {
    return <div className="twc-empty-msg">awaiting samples for graph</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
