interface BigReadoutProps {
  value: number | null | undefined;
  unit?: string;
  digits?: number;
  tone?: 'cool' | 'warm' | 'hot' | 'default';
  secondary?: string;
  emptyLabel?: string;
}

function formatValue(v: number, digits: number): string {
  return digits === 0 ? Math.round(v).toString() : v.toFixed(digits);
}

export function BigReadout({
  value,
  unit,
  digits = 0,
  tone = 'default',
  secondary,
  emptyLabel = '— —',
}: BigReadoutProps) {
  const isEmpty = value === null || value === undefined || Number.isNaN(value);
  return (
    <div className="twc-readout">
      <div className="twc-readout-value" data-tone={tone === 'default' ? undefined : tone}>
        {isEmpty ? emptyLabel : formatValue(value, digits)}
      </div>
      {unit && <div className="twc-readout-unit">{unit}</div>}
      {secondary && !isEmpty && <div className="twc-readout-secondary">{secondary}</div>}
    </div>
  );
}
