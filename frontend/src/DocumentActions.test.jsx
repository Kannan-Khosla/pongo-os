import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DocumentActions, { previewDocumentUrl } from './DocumentActions';


describe('DocumentActions', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('previews a fetched PDF in-app and keeps both downloads available', async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => 'blob:pongo-record');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      blob: () => Promise.resolve(new Blob(['%PDF-record'], { type: 'application/pdf' })),
    })));

    render(<DocumentActions csvUrl="/api/receipts/12/export" pdfUrl="/api/receipts/12/pdf" title="Receipt REC-0012" />);

    expect(screen.getByRole('link', { name: 'PDF' })).toHaveAttribute('href', '/api/receipts/12/pdf');
    expect(screen.getByRole('link', { name: 'CSV' })).toHaveAttribute('href', '/api/receipts/12/export');
    const trigger = screen.getByRole('button', { name: 'Preview' });
    await user.click(trigger);

    expect(screen.getByRole('dialog', { name: 'Receipt REC-0012' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTitle('Receipt REC-0012 PDF preview')).toHaveAttribute('src', 'blob:pongo-record'));
    expect(fetch).toHaveBeenCalledWith('/api/receipts/12/pdf?preview=true', expect.objectContaining({ credentials: 'include' }));

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:pongo-record');
  });

  it('appends the preview flag without discarding an existing query', () => {
    expect(previewDocumentUrl('/api/document.pdf?version=2')).toBe('/api/document.pdf?version=2&preview=true');
  });
});
