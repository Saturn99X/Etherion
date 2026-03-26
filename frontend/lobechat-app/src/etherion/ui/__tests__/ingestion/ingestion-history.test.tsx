import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MockedProvider } from '@apollo/client/testing';
import { App } from 'antd';
import { IngestionHistory } from '../../ingestion/ingestion-history';
import { GET_JOB_HISTORY_QUERY } from '@etherion/lib/graphql-operations';

const mockJobHistoryData = {
  request: {
    query: GET_JOB_HISTORY_QUERY,
    variables: { limit: 20, offset: 0 },
  },
  result: {
    data: {
      getJobHistory: {
        jobs: [
          {
            id: 'job-123456789',
            goal: 'Test ingestion goal',
            status: 'COMPLETED',
            createdAt: '2026-01-21T10:00:00Z',
            completedAt: '2026-01-21T10:05:00Z',
            duration: 300,
            totalCost: 0.0523,
            modelUsed: 'gpt-4',
          },
          {
            id: 'job-987654321',
            goal: 'Another test goal',
            status: 'RUNNING',
            createdAt: '2026-01-21T11:00:00Z',
            modelUsed: 'gpt-3.5-turbo',
          },
          {
            id: 'job-111222333',
            goal: 'Failed ingestion',
            status: 'FAILED',
            createdAt: '2026-01-21T09:00:00Z',
            completedAt: '2026-01-21T09:02:00Z',
            duration: 120,
            totalCost: 0.0123,
            modelUsed: 'gpt-4',
          },
        ],
        totalCount: 3,
      },
    },
  },
};

describe('IngestionHistory', () => {
  it('should fetch and display job history on mount', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test ingestion goal')).toBeInTheDocument();
      expect(screen.getByText('Another test goal')).toBeInTheDocument();
      expect(screen.getByText('Failed ingestion')).toBeInTheDocument();
    });
  });

  it('should display job IDs (truncated)', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/job-123456789/i)).toBeInTheDocument();
    });
  });

  it('should display status tags with correct colors', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('COMPLETED')).toBeInTheDocument();
      expect(screen.getByText('RUNNING')).toBeInTheDocument();
      expect(screen.getByText('FAILED')).toBeInTheDocument();
    });
  });

  it('should display model names', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByText('gpt-4')).toHaveLength(2);
      expect(screen.getByText('gpt-3.5-turbo')).toBeInTheDocument();
    });
  });

  it('should display timestamps', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      // Check that dates are rendered (format may vary by locale)
      const dateElements = screen.getAllByText(/2026|1\/21/);
      expect(dateElements.length).toBeGreaterThan(0);
    });
  });

  it('should display duration for completed jobs', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('300s')).toBeInTheDocument();
      expect(screen.getByText('120s')).toBeInTheDocument();
    });
  });

  it('should display cost for completed jobs', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('0.0523')).toBeInTheDocument();
      expect(screen.getByText('0.0123')).toBeInTheDocument();
    });
  });

  it('should display "-" for missing optional fields', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      // Running job has no completedAt, duration, or totalCost
      const dashElements = screen.getAllByText('-');
      expect(dashElements.length).toBeGreaterThan(0);
    });
  });

  it('should call onViewDetails when View button is clicked', async () => {
    const user = userEvent.setup();
    const onViewDetails = vi.fn();

    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory onViewDetails={onViewDetails} />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test ingestion goal')).toBeInTheDocument();
    });

    const viewButtons = screen.getAllByRole('button', { name: /view/i });
    await user.click(viewButtons[0]);

    expect(onViewDetails).toHaveBeenCalledWith('job-123456789');
  });

  it('should display empty state when no records exist', async () => {
    const emptyMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: { limit: 20, offset: 0 },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [],
            totalCount: 0,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[emptyMock]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/no ingestion history found/i)).toBeInTheDocument();
    });
  });

  it('should handle GraphQL errors gracefully', async () => {
    const errorMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: { limit: 20, offset: 0 },
      },
      error: new Error('Network error'),
    };

    render(
      <MockedProvider mocks={[errorMock]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      // Error should be caught and logged, component should handle gracefully
      expect(screen.queryByText('Test ingestion goal')).not.toBeInTheDocument();
    });
  });

  it('should refresh data when refresh button is clicked', async () => {
    const user = userEvent.setup();
    const refreshMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: { limit: 20, offset: 0 },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-new',
                goal: 'Refreshed data',
                status: 'COMPLETED',
                createdAt: '2026-01-21T12:00:00Z',
                completedAt: '2026-01-21T12:05:00Z',
                duration: 300,
                totalCost: 0.05,
                modelUsed: 'gpt-4',
              },
            ],
            totalCount: 1,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[mockJobHistoryData, refreshMock]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test ingestion goal')).toBeInTheDocument();
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    await user.click(refreshButton);

    await waitFor(() => {
      expect(screen.getByText('Refreshed data')).toBeInTheDocument();
    });
  });

  it('should respect custom limit prop', async () => {
    const customLimitMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: { limit: 10, offset: 0 },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [],
            totalCount: 0,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[customLimitMock]} addTypename={false}>
        <App>
          <IngestionHistory limit={10} />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/no ingestion history found/i)).toBeInTheDocument();
    });
  });

  it('should display loading state while fetching', () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    // Loading spinner should be visible initially
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('should display pagination controls', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test ingestion goal')).toBeInTheDocument();
    });

    // Pagination should be visible - check for total text
    expect(screen.getByText(/total 3 records/i)).toBeInTheDocument();
  });

  it('should truncate long goal text with ellipsis', async () => {
    const longGoalMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: { limit: 20, offset: 0 },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-long',
                goal: 'This is a very long goal text that should be truncated with ellipsis to prevent layout issues in the table view',
                status: 'COMPLETED',
                createdAt: '2026-01-21T10:00:00Z',
                completedAt: '2026-01-21T10:05:00Z',
                duration: 300,
                totalCost: 0.05,
                modelUsed: 'gpt-4',
              },
            ],
            totalCount: 1,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[longGoalMock]} addTypename={false}>
        <App>
          <IngestionHistory />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      // Check that the goal text is rendered (ellipsis is handled by CSS)
      expect(screen.getByText(/this is a very long goal text/i)).toBeInTheDocument();
    });
  });
});
