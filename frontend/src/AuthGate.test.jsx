import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import AuthGate from './AuthGate';

afterEach(() => vi.unstubAllGlobals());

function Workspace({ currentUser, onLogout }) {
  return <><div>Protected Pongo workspace</div>{currentUser && <button onClick={onLogout} type="button">Workspace sign out</button>}</>;
}

it('shows registration after an unauthenticated check and opens the app after success', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ authenticated: true, user: { id: 1, email: 'staff@example.com', display_name: 'Kannan' } }) }));
  const user = userEvent.setup();
  render(<AuthGate><Workspace /></AuthGate>);

  await user.click(await screen.findByRole('tab', { name: 'Register' }));
  await user.type(screen.getByLabelText('Display name'), 'Kannan');
  await user.type(screen.getByLabelText('Email address'), 'staff@example.com');
  await user.type(screen.getByLabelText('Password'), 'correct-horse-battery-staple');
  await user.click(screen.getByRole('button', { name: 'Create account' }));

  expect(await screen.findByText('Protected Pongo workspace')).toBeInTheDocument();
  await waitFor(() => expect(fetch.mock.calls[1][1].credentials).toBe('include'));
});

it('passes the authenticated user and logout action into the workspace', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ authenticated: true, user: { id: 1, email: 'staff@example.com', display_name: 'Kannan' } }) })
    .mockResolvedValueOnce({ ok: true, status: 204 }));
  const user = userEvent.setup();
  render(<AuthGate><Workspace /></AuthGate>);

  await user.click(await screen.findByRole('button', { name: 'Workspace sign out' }));

  expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  expect(fetch.mock.calls[1][0]).toContain('/api/auth/logout');
});
