import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, Eye, FileSpreadsheet, FileText, LoaderCircle, X } from 'lucide-react';
import { apiFetch } from './api';
import './DocumentActions.css';


export function previewDocumentUrl(pdfUrl) {
  return `${pdfUrl}${pdfUrl.includes('?') ? '&' : '?'}preview=true`;
}


function PdfPreviewDialog({ title, pdfUrl, csvUrl, onClose }) {
  const headingId = useId();
  const panelRef = useRef(null);
  const closeRef = useRef(null);
  const [objectUrl, setObjectUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    let generatedUrl = '';
    setObjectUrl('');
    setError('');
    apiFetch(previewDocumentUrl(pdfUrl), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(typeof body?.detail === 'string' ? body.detail : 'The PDF preview could not be loaded.');
        }
        const blob = await response.blob();
        generatedUrl = URL.createObjectURL(blob);
        setObjectUrl(generatedUrl);
      })
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message || 'The PDF preview could not be loaded.');
      });
    return () => {
      controller.abort();
      if (generatedUrl) URL.revokeObjectURL(generatedUrl);
    };
  }, [pdfUrl]);

  useEffect(() => {
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = [...(panelRef.current?.querySelectorAll('button:not([disabled]), a[href], iframe') || [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, [onClose]);

  return createPortal(
    <div className="document-preview-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-labelledby={headingId} aria-modal="true" className="document-preview-dialog" ref={panelRef} role="dialog">
        <header className="document-preview-header">
          <div>
            <span>Document record / live preview</span>
            <h2 id={headingId}>{title}</h2>
            <p>Review the complete PDF without leaving Pongo OS.</p>
          </div>
          <div className="document-preview-header-actions">
            <a href={pdfUrl}><Download size={16} aria-hidden="true" />PDF</a>
            {csvUrl && <a href={csvUrl}><FileSpreadsheet size={16} aria-hidden="true" />CSV</a>}
            <button aria-label="Close document preview" onClick={onClose} ref={closeRef} type="button"><X size={20} aria-hidden="true" /></button>
          </div>
        </header>
        <div aria-busy={!objectUrl && !error} className="document-preview-canvas">
          {!objectUrl && !error && <div className="document-preview-loading" role="status"><LoaderCircle aria-hidden="true" />Preparing PDF preview…</div>}
          {error && <div className="document-preview-error" role="alert"><FileText aria-hidden="true" /><strong>Preview unavailable</strong><span>{error}</span><a href={pdfUrl}>Download the PDF instead</a></div>}
          {objectUrl && <iframe src={objectUrl} title={`${title} PDF preview`} />}
        </div>
      </section>
    </div>,
    document.body,
  );
}


export default function DocumentActions({ title, pdfUrl, csvUrl, compact = false }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  return (
    <>
      <div className={`document-actions${compact ? ' compact' : ''}`} onClick={(event) => event.stopPropagation()}>
        <button aria-haspopup="dialog" className="document-preview-trigger" onClick={() => setPreviewOpen(true)} type="button"><Eye size={16} aria-hidden="true" />Preview</button>
        <a href={pdfUrl}><Download size={16} aria-hidden="true" />PDF</a>
        {csvUrl && <a href={csvUrl}><FileSpreadsheet size={16} aria-hidden="true" />CSV</a>}
      </div>
      {previewOpen && <PdfPreviewDialog csvUrl={csvUrl} onClose={() => setPreviewOpen(false)} pdfUrl={pdfUrl} title={title} />}
    </>
  );
}
