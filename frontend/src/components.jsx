export function Button({ variant = 'secondary', size = 'md', disabled = false, onClick, children, ...props }) {
  const className = variant === 'primary' ? 'primary-button' : variant === 'ghost' ? 'muted-button' : 'action-button';
  return (
    <button className={`${className} button-${size}`} disabled={disabled} onClick={onClick} type="button" {...props}>
      {children}
    </button>
  );
}

export function DataTable({ columns, rows, loading = false, emptyMessage = 'No rows found.' }) {
  return (
    <div className="table-wrap table-card">
      <div className="table-scroll" data-testid="table-scroll-container">
        <table className="data-table">
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={columns.length}>Loading...</td></tr>}
            {!loading && rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{row[column]}</td>)}</tr>)}
            {!loading && rows.length === 0 && <tr><td colSpan={columns.length}><div className="empty-table-row">{emptyMessage}</div></td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FilterBar({ value, onChange, onClear }) {
  return (
    <div className="filter-panel">
      <label className="field">
        <span>Search</span>
        <div className="input-with-icon">
          <input aria-label="Search" value={value} onChange={(event) => onChange(event.target.value)} type="search" />
        </div>
      </label>
      <button className="muted-button" onClick={onClear} type="button">Clear</button>
    </div>
  );
}
