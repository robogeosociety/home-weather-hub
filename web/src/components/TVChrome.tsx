import type { ReactNode } from 'react';
import { useLayout } from '../state/layout';
import { useSettings } from '../state/settings';
import type { WidgetState } from '../state/live';

export interface TVChromeProps {
  widgetId: string;
  title: string;
  stat?: string;
  state: WidgetState;
  display?: 'big-number' | 'graph';
  onDisplayChange?: (d: 'big-number' | 'graph') => void;
  showDisplayToggle?: boolean;
  children: ReactNode;
}

export function TVChrome({
  widgetId,
  title,
  stat,
  state,
  display,
  onDisplayChange,
  showDisplayToggle,
  children,
}: TVChromeProps) {
  const editMode = useSettings((s) => s.editMode);
  const removeWidget = useLayout((s) => s.removeWidget);
  return (
    <div className="twc-chrome">
      <div className="twc-chrome-header">
        <span className="twc-chrome-state" data-state={state} aria-label={state} />
        <div className="twc-chrome-title">
          <span>{title}</span>
          {stat && stat !== 'current' && <span className="twc-chrome-stat">{stat}</span>}
        </div>
        {editMode && (
          <button
            type="button"
            className="twc-chrome-remove"
            title={`Remove ${title}`}
            aria-label={`Remove ${title} widget`}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => removeWidget(widgetId)}
          >
            ×
          </button>
        )}
      </div>
      {showDisplayToggle && display && onDisplayChange && (
        <div className="twc-chrome-display-toggle" onMouseDown={(e) => e.stopPropagation()}>
          <button
            type="button"
            data-active={display === 'big-number'}
            onClick={() => onDisplayChange('big-number')}
          >
            NUM
          </button>
          <button
            type="button"
            data-active={display === 'graph'}
            onClick={() => onDisplayChange('graph')}
          >
            GRAPH
          </button>
        </div>
      )}
      <div className="twc-chrome-body" style={{ containerType: 'inline-size' }}>
        {children}
      </div>
    </div>
  );
}
