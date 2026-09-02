import { useId, useRef, useState } from 'react';

export function multiSelectValues(value) {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return [...new Set(values.map((entry) => String(entry).trim()).filter(Boolean))];
}

export default function MultiSelectFilter({
  label,
  value,
  options,
  onChange,
  disabled = false,
  className = 'field',
  allLabel = `All ${label.toLowerCase()}s`,
  formatOption = String,
}) {
  const id = useId();
  const detailsRef = useRef(null);
  const summaryRef = useRef(null);
  const [search, setSearch] = useState('');
  const selected = multiSelectValues(value);
  const choices = [...new Set([...selected, ...(options || []).map(String)].filter(Boolean))];
  const visibleChoices = choices.filter((option) => formatOption(option).toLowerCase().includes(search.trim().toLowerCase()));
  const summary = selected.length === 0
    ? allLabel
    : selected.length === 1
      ? formatOption(selected[0])
      : `${selected.length} brands selected`;

  function toggle(option, checked) {
    onChange(checked ? [...selected, option] : selected.filter((value) => value !== option));
  }

  function close() {
    if (detailsRef.current) detailsRef.current.open = false;
    setSearch('');
    summaryRef.current?.focus();
  }

  return (
    <div className={`${className} multi-select-field`}>
      <span id={`${id}-label`}>{label}</span>
      <details
        className="multi-select"
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            close();
          }
        }}
        ref={detailsRef}
      >
        <summary
          aria-disabled={disabled || undefined}
          aria-labelledby={`${id}-label ${id}-summary`}
          onClick={(event) => {
            if (disabled) event.preventDefault();
          }}
          ref={summaryRef}
        >
          <span id={`${id}-summary`}>{summary}</span>
        </summary>
        <div className="multi-select-menu">
          {choices.length > 10 && (
            <input
              aria-label={`Search ${label.toLowerCase()}s`}
              autoComplete="off"
              onChange={(event) => setSearch(event.target.value)}
              placeholder={`Find a ${label.toLowerCase()}`}
              value={search}
            />
          )}
          <div aria-label={`${label} options`} className="multi-select-options" role="group">
            {visibleChoices.map((option, index) => (
              <label htmlFor={`${id}-${index}`} key={option}>
                <input
                  checked={selected.includes(option)}
                  id={`${id}-${index}`}
                  onChange={(event) => toggle(option, event.target.checked)}
                  type="checkbox"
                />
                <span>{formatOption(option)}</span>
              </label>
            ))}
            {visibleChoices.length === 0 && <small>No brands found.</small>}
          </div>
          <div className="multi-select-actions">
            <button disabled={selected.length === 0} onClick={() => onChange([])} type="button">Clear</button>
            <button onClick={close} type="button">Done</button>
          </div>
        </div>
      </details>
    </div>
  );
}
