export default function MetricCard({ label, value, meta, tone = 'aqua', compact = false }) {
  return (
    <article className={`metric-card metric-card--${tone}${compact ? ' metric-card--compact' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {meta && <small>{meta}</small>}
    </article>
  );
}
