import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MobileCodeScanner from './MobileCodeScanner';

const scannerMocks = vi.hoisted(() => ({
  decodeFromConstraints: vi.fn(),
}));

vi.mock('@zxing/browser', () => ({
  BrowserMultiFormatReader: class BrowserMultiFormatReader {
    decodeFromConstraints(...args) {
      return scannerMocks.decodeFromConstraints(...args);
    }
  },
}));

describe('MobileCodeScanner', () => {
  let controls;

  beforeEach(() => {
    controls = { stop: vi.fn() };
    scannerMocks.decodeFromConstraints.mockReset();
    scannerMocks.decodeFromConstraints.mockResolvedValue(controls);
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
  });

  it('starts the rear camera and returns a detected item code', async () => {
    const onClose = vi.fn();
    const onDetected = vi.fn();
    render(<MobileCodeScanner open onClose={onClose} onDetected={onDetected} />);

    await waitFor(() => expect(scannerMocks.decodeFromConstraints).toHaveBeenCalledOnce());
    const [constraints, , callback] = scannerMocks.decodeFromConstraints.mock.calls[0];
    expect(constraints.video.facingMode).toEqual({ ideal: 'environment' });

    act(() => callback({ getText: () => ' 012345678905 ' }, undefined, controls));

    expect(onDetected).toHaveBeenCalledWith('012345678905');
    expect(onClose).toHaveBeenCalledOnce();
    expect(controls.stop).toHaveBeenCalled();
  });

  it('explains blocked camera permission and keeps manual search available', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onDetected = vi.fn();
    scannerMocks.decodeFromConstraints.mockRejectedValue(Object.assign(new Error('blocked'), { name: 'NotAllowedError' }));
    render(<MobileCodeScanner open onClose={onClose} onDetected={onDetected} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Camera access is blocked');
    await user.type(screen.getByLabelText('Enter barcode or SKU instead'), 'PONGO-100');
    await user.click(screen.getByRole('button', { name: 'Search item' }));

    expect(onDetected).toHaveBeenCalledWith('PONGO-100');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('can retry the camera after a temporary permission error', async () => {
    const user = userEvent.setup();
    scannerMocks.decodeFromConstraints
      .mockRejectedValueOnce(Object.assign(new Error('blocked'), { name: 'NotAllowedError' }))
      .mockResolvedValueOnce(controls);
    render(<MobileCodeScanner open onClose={() => {}} onDetected={() => {}} />);

    await user.click(await screen.findByRole('button', { name: 'Try camera again' }));

    await waitFor(() => expect(scannerMocks.decodeFromConstraints).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Hold steady and fill the frame with one code.')).toBeInTheDocument();
  });

  it('stops the camera when the scanner closes', async () => {
    const { rerender } = render(<MobileCodeScanner open onClose={() => {}} onDetected={() => {}} />);
    await waitFor(() => expect(scannerMocks.decodeFromConstraints).toHaveBeenCalledOnce());
    rerender(<MobileCodeScanner open={false} onClose={() => {}} onDetected={() => {}} />);

    expect(controls.stop).toHaveBeenCalled();
  });
});
