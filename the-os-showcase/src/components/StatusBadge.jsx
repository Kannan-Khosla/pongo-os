export default function StatusBadge({ children, tone = 'neutral' }) {
  return <span className={`status-badge status-badge--${tone}`}><i aria-hidden="true" />{children}</span>;
}
