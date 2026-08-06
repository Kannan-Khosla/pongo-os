export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');

let activeRequests = 0;
const activityListeners = new Set();
const inFlightGetRequests = new Map();

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
  const method = String(init.method || 'GET').toUpperCase();
  const requestKey = method === 'GET' && !init.signal ? String(input) : null;
  if (requestKey && inFlightGetRequests.has(requestKey)) {
    const response = await inFlightGetRequests.get(requestKey);
    return typeof response.clone === 'function' ? response.clone() : response;
  }

  activeRequests += 1;
  if (activeRequests === 1) notifyActivityListeners();
  const request = globalThis.fetch(input, { credentials: 'include', ...init });
  if (requestKey) inFlightGetRequests.set(requestKey, request);
  try {
    const response = await request;
    return requestKey && typeof response.clone === 'function' ? response.clone() : response;
  } finally {
    if (requestKey) inFlightGetRequests.delete(requestKey);
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests === 0) notifyActivityListeners();
  }
}
