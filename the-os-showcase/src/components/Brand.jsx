export default function Brand({ compact = false }) {
  return (
    <span className={`brand${compact ? ' brand--compact' : ''}`}>
      <span className="brand__mark" aria-hidden="true"><i /><i /><i /></span>
      <span>The-OS</span>
    </span>
  );
}
