import { useEffect, useMemo, useRef, useState } from 'react';
import { Responsive, WidthProvider, type Layout } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import type { Breakpoint, WidgetConfig } from '../api/types';
import { useLayout } from '../state/layout';
import { useSettings } from '../state/settings';
import { MetricWidget } from './widgets/MetricWidget';
import { WindWidget } from './widgets/WindWidget';
import { StrikesWidget } from './widgets/StrikesWidget';

const ResponsiveGrid = WidthProvider(Responsive);

const BREAKPOINTS: Record<Breakpoint, number> = {
  tv: 1920,
  mac: 1280,
  tablet: 768,
  phone: 0,
};

const COLS: Record<Breakpoint, number> = {
  tv: 12,
  mac: 10,
  tablet: 6,
  phone: 2,
};

function renderWidget(config: WidgetConfig) {
  if (config.kind === 'wind') return <WindWidget config={config} />;
  if (config.kind === 'strikes') return <StrikesWidget config={config} />;
  return <MetricWidget config={config} />;
}

export function Dashboard() {
  const widgets = useLayout((s) => s.widgets);
  const layouts = useLayout((s) => s.layouts);
  const setLayoutForBreakpoint = useLayout((s) => s.setLayoutForBreakpoint);
  const editMode = useSettings((s) => s.editMode);
  const [currentBreakpoint, setCurrentBreakpoint] = useState<Breakpoint>('mac');
  const dashboardRef = useRef<HTMLDivElement>(null);
  const [rowHeight, setRowHeight] = useState(60);

  // Re-fit row height to the available viewport so the grid is full-screen on
  // Mac/iPad/TV. Phone scrolls — we use a fixed row height there.
  useEffect(() => {
    const calc = () => {
      if (currentBreakpoint === 'phone') {
        setRowHeight(72);
        return;
      }
      const vh = dashboardRef.current?.clientHeight ?? window.innerHeight;
      // We aim for the layouts above to stack to roughly 10 rows on mac/tv,
      // 18 on tablet. Use the max y+h of the current layout to fit perfectly.
      const items = layouts[currentBreakpoint] ?? [];
      const totalRows = Math.max(8, ...items.map((i) => i.y + i.h));
      const margin = 10 * (totalRows + 1);
      setRowHeight(Math.max(40, Math.floor((vh - margin) / totalRows)));
    };
    calc();
    window.addEventListener('resize', calc);
    return () => window.removeEventListener('resize', calc);
  }, [currentBreakpoint, layouts]);

  const rgLayouts = useMemo(() => {
    return {
      tv: layouts.tv,
      mac: layouts.mac,
      tablet: layouts.tablet,
      phone: layouts.phone,
    };
  }, [layouts]);

  const fixed = currentBreakpoint !== 'phone';

  return (
    <div className={`twc-dashboard ${fixed ? 'is-fixed' : ''}`} ref={dashboardRef}>
      <div className="twc-grid-bg" />
      <ResponsiveGrid
        layouts={rgLayouts}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={rowHeight}
        margin={[10, 10]}
        containerPadding={[0, 0]}
        isDraggable={editMode}
        isResizable={editMode}
        compactType="vertical"
        preventCollision={false}
        onBreakpointChange={(bp) => setCurrentBreakpoint(bp as Breakpoint)}
        onLayoutChange={(_layout: Layout[], all) => {
          // Only persist when the user is editing — otherwise the resize-fit
          // effect would write on every viewport change.
          if (!editMode) return;
          for (const bp of Object.keys(all) as Breakpoint[]) {
            setLayoutForBreakpoint(bp, all[bp] as Layout[]);
          }
        }}
      >
        {widgets.map((w) => (
          <div key={w.i}>{renderWidget(w)}</div>
        ))}
      </ResponsiveGrid>
    </div>
  );
}
