import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getJobCost, getUsageByProvider, getUsageSummary } from '../usage';

const queryMock = vi.fn();

vi.mock('@etherion/lib/apollo-client', () => ({
  getClient: () => ({
    query: queryMock,
  }),
}));

beforeEach(() => {
  queryMock.mockReset();
});

describe('etherion bridge: usage.ts', () => {
  it('getUsageSummary maps jobs and aggregates totalCostUsd', async () => {
    queryMock.mockResolvedValueOnce({
      data: {
        getJobHistory: {
          jobs: [
            {
              id: 'job1',
              goal: 'g1',
              status: 'completed',
              createdAt: '2025-01-01T00:00:00Z',
              completedAt: '2025-01-01T00:05:00Z',
              duration: '5m',
              totalCost: '$10.50',
              modelUsed: 'modelA',
              tokenCount: 1000,
              successRate: 1.0,
            },
            {
              id: 'job2',
              goal: 'g2',
              status: 'completed',
              createdAt: '2025-01-02T00:00:00Z',
              completedAt: '2025-01-02T00:03:00Z',
              duration: '3m',
              totalCost: '$2.00',
              modelUsed: 'modelB',
              tokenCount: 500,
              successRate: 0.9,
            },
          ],
          totalCount: 2,
          pageInfo: { hasNextPage: false, hasPreviousPage: false },
        },
      },
    });

    const summary = await getUsageSummary({
      limit: 10,
      offset: 5,
      status: 'completed',
      dateFrom: '2025-01-01',
      dateTo: '2025-01-31',
    });

    expect(queryMock).toHaveBeenCalledTimes(1);
    expect(queryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          limit: 10,
          offset: 5,
          status: 'completed',
          date_from: '2025-01-01',
          date_to: '2025-01-31',
        },
      }),
    );

    expect(summary.totalJobs).toBe(2);
    expect(summary.jobs).toHaveLength(2);
    expect(summary.totalCostUsd).toBeCloseTo(12.5);

    expect(summary.jobs[0].totalCostUsd).toBeCloseTo(10.5);
    expect(summary.jobs[1].totalCostUsd).toBeCloseTo(2.0);
  });

  it('getJobCost enforces non-empty jobId', async () => {
    await expect(getJobCost('')).rejects.toThrow('jobId is required');
  });

  it('getJobCost reads numeric and string total_cost correctly', async () => {
    queryMock.mockResolvedValueOnce({
      data: {
        getJobDetails: {
          output_data: {
            total_cost: 4.25,
          },
        },
      },
    });

    const numericCost = await getJobCost('job-numeric');
    expect(numericCost).toBeCloseTo(4.25);

    queryMock.mockResolvedValueOnce({
      data: {
        getJobDetails: {
          output_data: {
            total_cost: '$3.50',
          },
        },
      },
    });

    const stringCost = await getJobCost('job-string');
    expect(stringCost).toBeCloseTo(3.5);

    queryMock.mockResolvedValueOnce({
      data: {
        getJobDetails: {
          output_data: {},
        },
      },
    });

    const zeroCost = await getJobCost('job-missing');
    expect(zeroCost).toBe(0);
  });

  it('getUsageByProvider groups by modelUsed and aggregates costs', async () => {
    queryMock.mockResolvedValueOnce({
      data: {
        getJobHistory: {
          jobs: [
            {
              id: 'job1',
              goal: 'g1',
              status: 'completed',
              createdAt: '2025-01-01T00:00:00Z',
              completedAt: '2025-01-01T00:05:00Z',
              duration: '5m',
              totalCost: '$1.00',
              modelUsed: 'modelA',
              tokenCount: 100,
              successRate: 1.0,
            },
            {
              id: 'job2',
              goal: 'g2',
              status: 'completed',
              createdAt: '2025-01-02T00:00:00Z',
              completedAt: '2025-01-02T00:03:00Z',
              duration: '3m',
              totalCost: '$2.00',
              modelUsed: 'modelA',
              tokenCount: 200,
              successRate: 0.9,
            },
            {
              id: 'job3',
              goal: 'g3',
              status: 'completed',
              createdAt: '2025-01-03T00:00:00Z',
              completedAt: '2025-01-03T00:04:00Z',
              duration: '4m',
              totalCost: '$3.00',
              modelUsed: 'modelB',
              tokenCount: 300,
              successRate: 0.8,
            },
          ],
          totalCount: 3,
          pageInfo: { hasNextPage: false, hasPreviousPage: false },
        },
      },
    });

    const byProvider = await getUsageByProvider();

    const entryA = byProvider.find((e) => e.model === 'modelA');
    const entryB = byProvider.find((e) => e.model === 'modelB');

    expect(entryA).toBeDefined();
    expect(entryA?.totalCostUsd).toBeCloseTo(3.0);
    expect(entryA?.jobCount).toBe(2);

    expect(entryB).toBeDefined();
    expect(entryB?.totalCostUsd).toBeCloseTo(3.0);
    expect(entryB?.jobCount).toBe(1);
  });
});
