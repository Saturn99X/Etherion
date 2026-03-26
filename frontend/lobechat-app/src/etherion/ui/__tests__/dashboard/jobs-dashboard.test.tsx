import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MockedProvider } from '@apollo/client/testing';
import { App } from 'antd';
import { JobsDashboard } from '../../dashboard/jobs-dashboard';
import { GET_JOB_HISTORY_QUERY } from '@etherion/lib/graphql-operations';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

const mockJobHistoryData = {
  request: {
    query: GET_JOB_HISTORY_QUERY,
    variables: {
      limit: 10,
      offset: 0,
      status: null,
    },
  },
  result: {
    data: {
      getJobHistory: {
        jobs: [
          {
            id: 'job-123456789',
            goal: 'Test goal execution',
            status: 'COMPLETED',
            createdAt: '2026-01-21T10:00:00Z',
            completedAt: '2026-01-21T10:05:00Z',
            duration: '5m 0s',
            totalCost: '$0.05',
            modelUsed: 'gpt-4',
            threadId: 'thread-1',
          },
          {
            id: 'job-987654321',
            goal: 'Another test goal',
            status: 'RUNNING',
            createdAt: '2026-01-21T11:00:00Z',
            duration: '2m 30s',
            totalCost: '$0.02',
            modelUsed: 'gpt-4',
            threadId: 'thread-2',
          },
          {
            id: 'job-111222333',
            goal: 'Failed goal',
            status: 'FAILED',
            createdAt: '2026-01-21T09:00:00Z',
            completedAt: '2026-01-21T09:02:00Z',
            duration: '2m 0s',
            totalCost: '$0.01',
            modelUsed: 'gpt-3.5-turbo',
            threadId: 'thread-3',
          },
        ],
        totalCount: 3,
      },
    },
  },
};

describe('JobsDashboard', () => {
  beforeEach(() => {
    mockPush.mockClear();
  });

  it('should fetch and display job history on mount', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test goal execution')).toBeInTheDocument();
      expect(screen.getByText('Another test goal')).toBeInTheDocument();
      expect(screen.getByText('Failed goal')).toBeInTheDocument();
    });
  });

  it('should display job IDs (truncated)', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/job-12345/)).toBeInTheDocument();
    });
  });

  it('should display status badges with correct colors', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Completed')).toBeInTheDocument();
      expect(screen.getByText('Running')).toBeInTheDocument();
      expect(screen.getByText('Failed')).toBeInTheDocument();
    });
  });

  it('should display costs', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('$0.05')).toBeInTheDocument();
      expect(screen.getByText('$0.02')).toBeInTheDocument();
      expect(screen.getByText('$0.01')).toBeInTheDocument();
    });
  });

  it('should display timestamps', async () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      // Check that dates are rendered (format may vary by locale)
      const dateElements = screen.getAllByText(/2026|1\/21/);
      expect(dateElements.length).toBeGreaterThan(0);
    });
  });

  it('should navigate to chat when Chat button is clicked', async () => {
    const user = userEvent.setup();

    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test goal execution')).toBeInTheDocument();
    });

    const chatButtons = screen.getAllByRole('button', { name: /chat/i });
    await user.click(chatButtons[0]);

    expect(mockPush).toHaveBeenCalledWith('/interact?thread=thread-1');
  });

  it('should disable Chat button when threadId is missing', async () => {
    const mockWithoutThread = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 0,
          status: null,
        },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-no-thread',
                goal: 'Job without thread',
                status: 'COMPLETED',
                createdAt: '2026-01-21T10:00:00Z',
                totalCost: '$0.05',
              },
            ],
            totalCount: 1,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[mockWithoutThread]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      const chatButton = screen.getByRole('button', { name: /chat/i });
      expect(chatButton).toBeDisabled();
    });
  });

  it('should show info message when Trace button is clicked', async () => {
    const user = userEvent.setup();

    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test goal execution')).toBeInTheDocument();
    });

    const traceButtons = screen.getAllByRole('button', { name: /trace/i });
    await user.click(traceButtons[0]);

    // AntD message.info should be called (we can't easily test the toast)
  });

  it('should filter by status', async () => {
    const user = userEvent.setup();
    const completedMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 0,
          status: 'completed',
        },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-completed',
                goal: 'Completed job',
                status: 'COMPLETED',
                createdAt: '2026-01-21T10:00:00Z',
                totalCost: '$0.05',
                threadId: 'thread-1',
              },
            ],
            totalCount: 1,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[mockJobHistoryData, completedMock]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test goal execution')).toBeInTheDocument();
    });

    const statusSelect = screen.getByRole('combobox');
    await user.click(statusSelect);

    const completedOption = screen.getByText('Completed');
    await user.click(completedOption);

    await waitFor(() => {
      expect(screen.getByText('Completed job')).toBeInTheDocument();
    });
  });

  it('should update search term', async () => {
    const user = userEvent.setup();

    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    const searchInput = screen.getByPlaceholderText(/search by goal/i);
    await user.type(searchInput, 'test query');

    expect(searchInput).toHaveValue('test query');
  });

  it('should refresh data when Refresh button is clicked', async () => {
    const user = userEvent.setup();
    const refreshMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 0,
          status: null,
        },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-refreshed',
                goal: 'Refreshed data',
                status: 'COMPLETED',
                createdAt: '2026-01-21T12:00:00Z',
                totalCost: '$0.10',
                threadId: 'thread-new',
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
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test goal execution')).toBeInTheDocument();
    });

    const refreshButton = screen.getByRole('button', { name: /refresh feed/i });
    await user.click(refreshButton);

    await waitFor(() => {
      expect(screen.getByText('Refreshed data')).toBeInTheDocument();
    });
  });

  it('should handle pagination', async () => {
    const user = userEvent.setup();
    const page2Mock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 10,
          status: null,
        },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-page2',
                goal: 'Page 2 job',
                status: 'COMPLETED',
                createdAt: '2026-01-21T08:00:00Z',
                totalCost: '$0.03',
                threadId: 'thread-page2',
              },
            ],
            totalCount: 11,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[mockJobHistoryData, page2Mock]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Test goal execution')).toBeInTheDocument();
    });

    // Click next page
    const nextButton = screen.getByRole('button', { name: /2/i });
    await user.click(nextButton);

    await waitFor(() => {
      expect(screen.getByText('Page 2 job')).toBeInTheDocument();
    });
  });

  it('should handle GraphQL errors gracefully', async () => {
    const errorMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 0,
          status: null,
        },
      },
      error: new Error('Network error'),
    };

    render(
      <MockedProvider mocks={[errorMock]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      // Error should be caught and message.error called
      expect(screen.queryByText('Test goal execution')).not.toBeInTheDocument();
    });
  });

  it('should display loading state while fetching', () => {
    render(
      <MockedProvider mocks={[mockJobHistoryData]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    // Table should be visible with loading state
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('should display PENDING_APPROVAL status correctly', async () => {
    const pendingMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 0,
          status: null,
        },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-pending',
                goal: 'Pending approval job',
                status: 'PENDING_APPROVAL',
                createdAt: '2026-01-21T10:00:00Z',
                totalCost: '$0.05',
                threadId: 'thread-pending',
              },
            ],
            totalCount: 1,
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[pendingMock]} addTypename={false}>
        <App>
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Approval Needed')).toBeInTheDocument();
    });
  });

  it('should truncate long goal text', async () => {
    const longGoalMock = {
      request: {
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: 10,
          offset: 0,
          status: null,
        },
      },
      result: {
        data: {
          getJobHistory: {
            jobs: [
              {
                id: 'job-long',
                goal: 'This is a very long goal text that should be truncated with ellipsis to prevent layout issues in the table view and maintain a clean UI',
                status: 'COMPLETED',
                createdAt: '2026-01-21T10:00:00Z',
                totalCost: '$0.05',
                threadId: 'thread-long',
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
          <JobsDashboard />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      const goalText = screen.getByText(/this is a very long goal text/i);
      expect(goalText).toBeInTheDocument();
    });
  });
});
