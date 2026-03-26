import { beforeEach, describe, expect, it, vi } from 'vitest';

import { checkHealth } from '../health';

const queryMock = vi.fn();

vi.mock('@etherion/lib/apollo-client', () => ({
  getClient: () => ({
    query: queryMock,
  }),
}));

beforeEach(() => {
  queryMock.mockReset();
});

describe('etherion bridge: health.ts', () => {
  it('checkHealth returns ok=true when backend returns a health_check string', async () => {
    queryMock.mockResolvedValueOnce({
      data: { health_check: 'GraphQL server is operational.' },
    });

    const status = await checkHealth();

    expect(queryMock).toHaveBeenCalledTimes(1);
    expect(status.ok).toBe(true);
    expect(status.message).toBe('GraphQL server is operational.');
  });

  it('checkHealth returns ok=false when backend response is invalid', async () => {
    queryMock.mockResolvedValueOnce({
      data: { health_check: null },
    } as any);

    const status = await checkHealth();

    expect(status.ok).toBe(false);
    expect(status.message).toBe('Invalid health_check response');
  });

  it('checkHealth returns ok=false when query throws', async () => {
    queryMock.mockRejectedValueOnce(new Error('Network down'));

    const status = await checkHealth();

    expect(status.ok).toBe(false);
    expect(status.message).toBe('Network down');
  });
});
