import { cloneElement, isValidElement, useEffect, useState } from 'react';
import { CheckCircle2, LogIn, ShieldCheck, UserPlus } from 'lucide-react';
import { API_BASE_URL, apiFetch } from './api';
import './AuthGate.css';

export default function AuthGate({ children }) {
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);
  const [mode, setMode] = useState('login');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiFetch(`${API_BASE_URL}/api/auth/me`)
      .then(async (response) => {
        if (response.status === 401) return { authenticated: false, auth_required: true };
        if (!response.ok) throw new Error('Unable to verify your session.');
        return response.json();
      })
      .then((body) => {
        setUser(body.user || null);
        setStatus(body.authenticated || body.auth_required === false ? 'ready' : 'signed-out');
      })
      .catch((requestError) => {
        setError(requestError.message);
        setStatus('signed-out');
      });
  }, []);

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    const form = new FormData(event.currentTarget);
    const payload = mode === 'register'
      ? {
          email: form.get('email'),
          display_name: form.get('display_name'),
          password: form.get('password'),
          registration_access_code: form.get('registration_access_code') || null,
        }
      : { email: form.get('email'), password: form.get('password') };
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to continue.');
      setUser(body.user);
      setStatus('ready');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function logout() {
    await apiFetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST' });
    setUser(null);
    setStatus('signed-out');
    setMode('login');
  }

  if (status === 'loading') return <main className="auth-loading" aria-live="polite">Checking secure session…</main>;
  if (status === 'signed-out') {
    return (
      <main className="auth-page">
        <section className="auth-brand" aria-labelledby="auth-heading">
          <div className="auth-brand-mark" aria-hidden="true">P</div>
          <p className="auth-eyebrow">Pongo Inventory OS / Secure access</p>
          <h1 id="auth-heading">Warehouse intelligence, kept inside.</h1>
          <p className="auth-brand-copy">Sign in to inventory, orders, receiving, WooCommerce operations, and legal-grade reporting.</p>
          <div className="auth-proof-grid"><span><ShieldCheck size={18} /> HttpOnly sessions</span><span><CheckCircle2 size={18} /> No role complexity</span></div>
        </section>
        <section className="auth-panel" aria-labelledby="auth-form-title">
          <div className="auth-step"><span>01</span><small>STAFF ACCESS</small></div>
          <h2 id="auth-form-title">{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
          <p>{mode === 'login' ? 'Use your Pongo staff account to continue.' : 'Use the staff registration code provided by an administrator.'}</p>
          <div className="auth-mode" role="tablist" aria-label="Account action">
            <button type="button" role="tab" aria-selected={mode === 'login'} onClick={() => { setMode('login'); setError(''); }}>Sign in</button>
            <button type="button" role="tab" aria-selected={mode === 'register'} onClick={() => { setMode('register'); setError(''); }}>Register</button>
          </div>
          <form onSubmit={submit}>
            {mode === 'register' && <label>Display name<input name="display_name" autoComplete="name" required maxLength="160" /></label>}
            <label>Email address<input name="email" type="email" autoComplete="email" required /></label>
            <label>Password<input name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 12 : 1} required /></label>
            {mode === 'register' && <label>Registration code <small>{import.meta.env.PROD ? 'Required in production' : 'Optional outside production'}</small><input name="registration_access_code" type="password" autoComplete="off" required={import.meta.env.PROD} /></label>}
            {error && <div className="auth-error" role="alert">{error}</div>}
            <button className="auth-submit" type="submit" disabled={submitting}>{mode === 'login' ? <LogIn size={18} /> : <UserPlus size={18} />}{submitting ? 'Please wait…' : mode === 'login' ? 'Sign in to Pongo OS' : 'Create account'}</button>
          </form>
        </section>
      </main>
    );
  }
  return isValidElement(children) ? cloneElement(children, { currentUser: user, onLogout: logout }) : children;
}
