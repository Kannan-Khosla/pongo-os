import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, getApiActivitySnapshot, subscribeToApiActivity } from './api.js';

describe('API activity', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('stays active until every overlapping request finishes', async () => {
    const resolvers = [];
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => resolvers.push(resolve))));
    const states = [];
    const unsubscribe = subscribeToApiActivity(() => states.push(getApiActivitySnapshot()));

    const first = apiFetch('/first');
    const second = apiFetch('/second');
    expect(getApiActivitySnapshot()).toBe(true);

    resolvers[0]({ ok: true });
    await first;
    expect(getApiActivitySnapshot()).toBe(true);

    resolvers[1]({ ok: true });
    await second;
    expect(getApiActivitySnapshot()).toBe(false);
    expect(states).toEqual([true, false]);
    unsubscribe();
  });

  it('shares one fetch for identical concurrent GET requests', async () => {
    let release;
    const response = { ok: true, clone: vi.fn(() => ({ ok: true })) };
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { release = () => resolve(response); })));

    const first = apiFetch('/same');
    const second = apiFetch('/same');

    expect(fetch).toHaveBeenCalledTimes(1);
    release();
    await expect(first).resolves.toEqual({ ok: true });
    await expect(second).resolves.toEqual({ ok: true });
    expect(response.clone).toHaveBeenCalledTimes(2);
  });
});
