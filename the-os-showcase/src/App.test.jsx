import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, test } from 'vitest';
import App from './App.jsx';
import Reveal from './components/Reveal.jsx';
import InteractiveOSWindow from './demo/InteractiveOSWindow.jsx';

function ShowcaseHarness() {
  const [activeModule, setActiveModule] = useState('command');
  return <InteractiveOSWindow activeModule={activeModule} onModuleChange={setActiveModule} />;
}

describe('The-OS interactive showcase', () => {
  test('navigates modules with tabs and keyboard controls', async () => {
    const user = userEvent.setup();
    render(<ShowcaseHarness />);
    const inventoryTab = screen.getByRole('tab', { name: 'Inventory' });
    await user.click(inventoryTab);
    expect(screen.getByRole('heading', { name: /one source of truth/i })).toBeInTheDocument();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('heading', { name: /every order/i })).toBeInTheDocument();
  });

  test('filters inventory and opens a product detail drawer', async () => {
    const user = userEvent.setup();
    render(<ShowcaseHarness />);
    await user.click(screen.getByRole('tab', { name: 'Inventory' }));
    await user.type(screen.getByRole('searchbox', { name: 'Search inventory' }), 'AeroCharge');
    expect(screen.getByText('1 products shown')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /AeroCharge Dock/i }));
    expect(screen.getByRole('dialog', { name: 'AeroCharge Dock' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close product details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('filters orders and reveals fulfillment detail', async () => {
    const user = userEvent.setup();
    render(<ShowcaseHarness />);
    await user.click(screen.getByRole('tab', { name: /^Orders/ }));
    await user.click(screen.getByRole('button', { name: /Ready/ }));
    expect(screen.getByText(/sample orders shown/)).toBeInTheDocument();
    const firstOrderButton = screen.getAllByRole('button', { name: /Open order/ })[0];
    await user.click(firstOrderButton);
    expect(screen.getByRole('dialog', { name: /Order #/ })).toBeInTheDocument();
  });

  test('completes the simulated scan-and-pick flow', async () => {
    const user = userEvent.setup();
    render(<ShowcaseHarness />);
    await user.click(screen.getByRole('tab', { name: 'Picking' }));
    expect(screen.getByText('2 / 4')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Demo scan' }));
    await user.click(screen.getByRole('button', { name: 'Demo scan' }));
    expect(screen.getByText('Pick complete')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Commit pick' }));
    expect(screen.getByText(/Four local stock movement rows recorded/i)).toBeInTheDocument();
  });

  test('accepts a receipt and updates its stock impact', async () => {
    const user = userEvent.setup();
    render(<ShowcaseHarness />);
    await user.click(screen.getByRole('tab', { name: 'Receiving' }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.click(screen.getByRole('button', { name: 'Accept delivery' }));
    expect(screen.getAllByText('Delivery accepted').length).toBeGreaterThan(0);
    expect(screen.getByText('+560 units posted')).toBeInTheDocument();
  });

  test('updates reports, insight ranges, and routes locally', async () => {
    const user = userEvent.setup();
    render(<ShowcaseHarness />);
    await user.click(screen.getByRole('tab', { name: 'Reports' }));
    await user.click(screen.getByRole('button', { name: 'Low stock' }));
    expect(screen.getByRole('heading', { name: 'Low stock' })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Insights' }));
    await user.click(screen.getByRole('button', { name: '90D' }));
    expect(screen.getByRole('img', { name: /^90D demand trend/ })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Routes' }));
    await user.click(screen.getByRole('button', { name: 'Finalize route' }));
    expect(screen.getByText(/controls locked/i)).toBeInTheDocument();
  });

  test('opens and closes the intentionally local request message', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getAllByRole('button', { name: /Request access/ })[0]);
    expect(screen.getByRole('dialog', { name: /intentionally not connected/i })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: /intentionally not connected/i })).not.toBeInTheDocument();
  });

  test('exposes the responsive navigation state', async () => {
    const user = userEvent.setup();
    render(<App />);
    const menuButton = screen.getByRole('button', { name: 'Open navigation' });
    await user.click(menuButton);
    expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('navigation', { name: 'Mobile navigation' })).toBeVisible();
  });

  test('reveals content immediately when reduced motion is requested', () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
    render(<Reveal>Reduced-motion content</Reveal>);
    expect(screen.getByText('Reduced-motion content')).toHaveAttribute('data-visible', 'true');
    window.matchMedia = originalMatchMedia;
  });
});
