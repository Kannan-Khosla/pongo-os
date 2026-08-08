import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Camera, Keyboard, RefreshCw, ScanLine, X } from 'lucide-react';
import './MobileCodeScanner.css';

const MAX_CODE_LENGTH = 512;

function cameraErrorMessage(error) {
  switch (error?.name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'Camera access is blocked. Allow camera access for Pongo OS in your browser settings, then try again.';
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'No camera was found on this device. Enter the barcode or SKU below instead.';
    case 'NotReadableError':
    case 'TrackStartError':
      return 'The camera is being used by another app. Close that app and try again.';
    case 'OverconstrainedError':
      return 'The rear camera could not be started. Enter the barcode or SKU below instead.';
    default:
      return 'The camera could not start. Check camera permission or enter the barcode or SKU below.';
  }
}

function stopVideo(video) {
  const stream = video?.srcObject;
  if (stream && typeof stream.getTracks === 'function') {
    stream.getTracks().forEach((track) => track.stop());
  }
  if (video) video.srcObject = null;
}

export default function MobileCodeScanner({ open, onClose, onDetected }) {
  const descriptionId = useId();
  const videoRef = useRef(null);
  const controlsRef = useRef(null);
  const closeButtonRef = useRef(null);
  const detectedRef = useRef(false);
  const [status, setStatus] = useState('starting');
  const [error, setError] = useState('');
  const [retryAvailable, setRetryAvailable] = useState(false);
  const [scanAttempt, setScanAttempt] = useState(0);
  const [manualCode, setManualCode] = useState('');

  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    function handleKeyDown(event) {
      if (event.key === 'Escape') onClose();
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return undefined;

    let cancelled = false;
    detectedRef.current = false;
    setStatus('starting');
    setError('');
    setRetryAvailable(false);
    setManualCode('');

    async function startCamera() {
      if (!window.isSecureContext && window.location.hostname !== 'localhost') {
        setStatus('error');
        setError('Camera scanning requires a secure HTTPS connection. Enter the barcode or SKU below instead.');
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('error');
        setError('Camera scanning is not supported by this browser. Enter the barcode or SKU below instead.');
        return;
      }

      try {
        const { BrowserMultiFormatReader } = await import('@zxing/browser');
        if (cancelled || !videoRef.current) return;

        const reader = new BrowserMultiFormatReader(undefined, {
          delayBetweenScanAttempts: 160,
          delayBetweenScanSuccess: 500,
        });
        const controls = await reader.decodeFromConstraints(
          {
            audio: false,
            video: {
              facingMode: { ideal: 'environment' },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
          },
          videoRef.current,
          (result, _scanError, activeControls) => {
            if (cancelled || detectedRef.current) return;
            if (result) {
              const value = result.getText()?.trim() || '';
              if (!value || value.length > MAX_CODE_LENGTH) {
                setStatus('error');
                setError('This code is empty or too long to search. Try another code or enter the SKU manually.');
                return;
              }
              detectedRef.current = true;
              activeControls.stop();
              stopVideo(videoRef.current);
              setStatus('success');
              navigator.vibrate?.(60);
              onDetected(value);
              onClose();
              return;
            }

          },
        );

        if (cancelled || detectedRef.current) {
          controls.stop();
          return;
        }
        controlsRef.current = controls;
        setStatus('scanning');
      } catch (cameraError) {
        if (!cancelled) {
          setStatus('error');
          setError(cameraErrorMessage(cameraError));
          setRetryAvailable(!['NotFoundError', 'DevicesNotFoundError'].includes(cameraError?.name));
        }
      }
    }

    startCamera();
    return () => {
      cancelled = true;
      controlsRef.current?.stop();
      controlsRef.current = null;
      stopVideo(videoRef.current);
    };
  }, [open, onClose, onDetected, scanAttempt]);

  if (!open || typeof document === 'undefined') return null;

  function submitManualCode(event) {
    event.preventDefault();
    const value = manualCode.trim();
    if (!value) {
      setError('Enter a barcode or SKU to search.');
      return;
    }
    if (value.length > MAX_CODE_LENGTH) {
      setError('The barcode or SKU is too long to search.');
      return;
    }
    detectedRef.current = true;
    controlsRef.current?.stop();
    stopVideo(videoRef.current);
    onDetected(value);
    onClose();
  }

  return createPortal(
    <div className="mobile-scanner-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }} role="presentation">
      <section aria-describedby={descriptionId} aria-label="Scan an item code" aria-modal="true" className="mobile-scanner-dialog" role="dialog">
        <header className="mobile-scanner-header">
          <div>
            <span className="mobile-scanner-kicker"><Camera aria-hidden="true" size={15} /> Phone camera</span>
            <h2>Scan an item code</h2>
            <p id={descriptionId}>Point the rear camera at a QR code, UPC, EAN, or Code 128 barcode.</p>
          </div>
          <button aria-label="Close camera scanner" className="mobile-scanner-close" onClick={onClose} ref={closeButtonRef} type="button">
            <X aria-hidden="true" size={22} />
          </button>
        </header>

        <div className="mobile-scanner-body">
          <div className="mobile-scanner-preview">
            <video aria-label="Live camera preview" autoPlay muted playsInline ref={videoRef} />
            <div aria-hidden="true" className="mobile-scanner-frame">
              <span />
            </div>
            {status === 'starting' && <div className="mobile-scanner-overlay" role="status"><span className="mobile-scanner-spinner" />Starting camera…</div>}
            {status === 'success' && <div className="mobile-scanner-overlay mobile-scanner-success" role="status">Code found</div>}
          </div>

          <div aria-live="polite" className="mobile-scanner-guidance">
            <ScanLine aria-hidden="true" size={19} />
            <span>{status === 'scanning' ? 'Hold steady and fill the frame with one code.' : 'Your browser may ask for camera permission.'}</span>
          </div>

          {error && (
            <div className="mobile-scanner-error" role="alert">
              <span>{error}</span>
              {retryAvailable && <button className="muted-button" onClick={() => setScanAttempt((current) => current + 1)} type="button"><RefreshCw aria-hidden="true" size={16} /> Try camera again</button>}
            </div>
          )}

          <form className="mobile-scanner-manual" onSubmit={submitManualCode}>
            <label htmlFor="mobile-scanner-manual-code"><Keyboard aria-hidden="true" size={18} /> Enter barcode or SKU instead</label>
            <div>
              <input
                autoComplete="off"
                id="mobile-scanner-manual-code"
                maxLength={MAX_CODE_LENGTH}
                onChange={(event) => {
                  setManualCode(event.target.value);
                  if (error) setError('');
                }}
                placeholder="Barcode or SKU"
                type="text"
                value={manualCode}
              />
              <button className="primary-button" type="submit">Search item</button>
            </div>
          </form>
        </div>
      </section>
    </div>,
    document.body,
  );
}
