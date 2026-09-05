import { useEffect, useRef } from 'react';
import { Check, X } from 'lucide-react';
import Brand from './Brand.jsx';

export default function LocalModal({ open, onClose }) {
  const closeRef = useRef(null);
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    closeRef.current?.focus();
    function handleKeyDown(event) {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab') return;
      const focusable = [...dialogRef.current.querySelectorAll('button, a, [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previous?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="local-modal glass-panel" role="dialog" aria-modal="true" aria-labelledby="walkthrough-title" ref={dialogRef}>
        <button className="icon-button local-modal__close" type="button" aria-label="Close walkthrough message" onClick={onClose} ref={closeRef}><X size={18} /></button>
        <Brand />
        <span className="local-modal__icon"><Check size={26} /></span>
        <h2 id="walkthrough-title">Demo contact experience intentionally not connected.</h2>
        <p>This standalone showcase never sends email, creates an account, or connects to a backend. The interaction ends here by design.</p>
        <button className="button button--primary" type="button" onClick={onClose}>Return to the showcase</button>
      </section>
    </div>
  );
}
