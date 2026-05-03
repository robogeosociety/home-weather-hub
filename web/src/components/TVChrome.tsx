import type { ReactNode } from 'react';
import type { WidgetState } from '../state/live';

export interface TVChromeProps {
  title: string;
  stat?: string;
  state: WidgetState;
  display?: 'big-number' | 'graph';
  onDisplayChange?: (d: 'big-number' | 'graph') => void;
  showDisplayToggle?: boolean;
  children: ReactNode;
}

export function TVChrome({
  title,
  stat,
  state,
  display,
  onDisplayChange,
  showDisplayToggle,
  children,
}: TVChromeProps) {
  return (
    <div className="twc-chrome">
      <div className="twc-chrome-header">
        <span className="twc-chrome-state" data-state={state} aria-label={state} />
        <div className="twc-chrome-title">
          <span>{title}</span>
          {stat && stat !== 'current' && <span className="twc-chrome-stat">{stat}</span>}
        </div>
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
