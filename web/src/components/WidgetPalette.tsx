import { WIDGET_PALETTE, useLayout } from '../state/layout';

export function WidgetPalette() {
  const widgets = useLayout((s) => s.widgets);
  const addWidget = useLayout((s) => s.addWidget);
  const removeWidget = useLayout((s) => s.removeWidget);
  const enabled = new Set(widgets.map((w) => w.i));

  return (
    <div className="twc-palette">
      <span className="twc-palette-label">Widgets</span>
      <div className="twc-palette-pills">
        {WIDGET_PALETTE.map((entry) => {
          const isOn = enabled.has(entry.i);
          return (
            <button
              key={entry.i}
              type="button"
              className="twc-pill"
              data-active={isOn}
              title={isOn ? `Hide ${entry.label}` : `Add ${entry.label} back to the dashboard`}
              onClick={() => (isOn ? removeWidget(entry.i) : addWidget(entry.i))}
            >
              <span className="twc-pill-dot" />
              {entry.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
