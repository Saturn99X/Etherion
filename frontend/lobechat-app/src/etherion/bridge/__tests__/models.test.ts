import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearThreadModel,
  getThreadModel,
  listAvailableModels,
  listAvailableProviders,
  setThreadModel,
} from '../models';

const state: any = {
  prefs: {},
  searchForce: {},
  getKey(threadId: string, branchId?: string) {
    return `${threadId}::${branchId ?? 'root'}`;
  },
  getPrefs(threadId: string, branchId?: string) {
    const key = state.getKey(threadId, branchId);
    return state.prefs[key] ?? {};
  },
  setPrefs: vi.fn((threadId: string, patch: any, branchId?: string) => {
    const key = state.getKey(threadId, branchId);
    state.prefs[key] = { ...(state.prefs[key] ?? {}), ...patch };
  }),
  clearPrefs: vi.fn((threadId: string, branchId?: string) => {
    const key = state.getKey(threadId, branchId);
    delete state.prefs[key];
  }),
};

vi.mock('@etherion/stores/thread-pref-store', () => ({
  useThreadPrefStore: {
    getState: () => state,
  },
  EMPTY_PREFS: Object.freeze({}),
}));

beforeEach(() => {
  state.prefs = {
    't1::root': { provider: 'openai', model: 'gpt-4' },
    't2::root': { provider: 'openai', model: 'gpt-4-mini' },
    't3::root': { provider: 'anthropic', model: 'claude-3' },
  };
  state.setPrefs.mockClear();
  state.clearPrefs.mockClear();
});

describe('etherion bridge: models.ts', () => {
  it('getThreadModel returns prefs for given thread/branch', () => {
    const prefs = getThreadModel('t1');
    expect(prefs).toEqual({ provider: 'openai', model: 'gpt-4' });
  });

  it('getThreadModel throws for empty threadId', () => {
    // @ts-expect-error
    expect(() => getThreadModel('')).toThrow(
      'threadId is required to read thread model preferences',
    );
  });

  it('setThreadModel writes provider/model via setPrefs', () => {
    setThreadModel('t1', 'b1', 'openai', 'gpt-4o');

    expect(state.setPrefs).toHaveBeenCalledWith('t1', {
      provider: 'openai',
      model: 'gpt-4o',
    }, 'b1');
  });

  it('setThreadModel throws for empty threadId', () => {
    // @ts-expect-error
    expect(() => setThreadModel('', undefined, 'openai', 'gpt-4o')).toThrow(
      'threadId is required to set thread model preferences',
    );
  });

  it('listAvailableProviders returns unique provider ids from prefs', () => {
    const providers = listAvailableProviders();
    expect(providers.sort()).toEqual(['anthropic', 'openai']);
  });

  it('listAvailableModels returns models for a given provider', () => {
    const openaiModels = listAvailableModels('openai').sort();
    expect(openaiModels).toEqual(['gpt-4', 'gpt-4-mini']);

    const anthropicModels = listAvailableModels('anthropic');
    expect(anthropicModels).toEqual(['claude-3']);
  });

  it('clearThreadModel delegates to clearPrefs when threadId is non-empty', () => {
    clearThreadModel('t1', 'b1');
    expect(state.clearPrefs).toHaveBeenCalledWith('t1', 'b1');
  });

  it('clearThreadModel is a no-op when threadId is empty', () => {
    // @ts-expect-error
    clearThreadModel('');
    expect(state.clearPrefs).not.toHaveBeenCalled();
  });
});
