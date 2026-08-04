export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');

let activeRequests = 0;
const activityListeners = new Set();

function notifyActivityListeners() {
  activityListeners.forEach((listener) => listener());
}

export function subscribeToApiActivity(listener) {
  activityListeners.add(listener);
  return () => activityListeners.delete(listener);
}

export function getApiActivitySnapshot() {
  return activeRequests > 0;
}

export async function apiFetch(input, init = {}) {
  activeRequests += 1;
  if (activeRequests === 1) notifyActivityListeners();
  try {
    return await globalThis.fetch(input, { credentials: 'include', ...init });
  } finally {
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests === 0) notifyActivityListeners();
  }
}
