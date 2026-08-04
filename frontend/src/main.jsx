import React, { useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import AuthGate from './AuthGate.jsx';
import { getApiActivitySnapshot, subscribeToApiActivity } from './api.js';
import './App.css';
import './PongoV2.css';

function GlobalActivityIndicator() {
  const isActive = useSyncExternalStore(subscribeToApiActivity, getApiActivitySnapshot, () => false);
  if (!isActive) return null;

  return (
    <div className="global-activity-indicator" role="status" aria-live="polite">
      <span className="global-activity-spinner" aria-hidden="true" />
      <span className="sr-only">Pongo OS is working</span>
    </div>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <GlobalActivityIndicator />
    <AuthGate><App /></AuthGate>
  </React.StrictMode>,
);
