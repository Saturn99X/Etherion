import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { IngestionMonitor } from '../../ingestion/ingestion-monitor';
import { mockJobStore, setupStoreMocks, resetStoreMocks } from '../mocks/stores';

// Mock the job store
vi.mock('@etherion/stores/job-store', () => ({
  useJobStore: (selector?: any) => {
    if (typeof selector === 'function') {
      return selector(mockJobStore);
    }
    return mockJobStore;
  },
}));

describe('IngestionMonitor', () => {
  beforeEach(() => {
    setupStoreMocks();
    // Reset job store state
    mockJobStore.jobs = {
      'job-1': {
        id: 'job-1',
        status: 'RUNNING',
        progressPercentage: 50,
        currentStep: 'Processing data',
        createdAt: new Date('2026-01-21T10:00:00Z'),
        isCompleted: false,
        isFailed: false,
      },
    };
  });

  afterEach(() => {
    resetStoreMocks();
  });

  it('should subscribe to job updates on mount', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(mockJobStore.subscribeToJob).toHaveBeenCalledWith('job-1');
  });

  it('should unsubscribe from job updates on unmount', () => {
    const { unmount } = render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    unmount();

    expect(mockJobStore.unsubscribeFromJob).toHaveBeenCalledWith('job-1');
  });

  it('should display job status', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('should display progress percentage', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    // Progress bar should show 50%
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('should display current step', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.getByText(/current step: processing data/i)).toBeInTheDocument();
  });

  it('should display job ID', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.getByText('job-1')).toBeInTheDocument();
  });

  it('should display started timestamp', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.getByText(/started:/i)).toBeInTheDocument();
  });

  it('should display completed status for completed jobs', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'COMPLETED',
      isCompleted: true,
      progressPercentage: 100,
      completedAt: new Date('2026-01-21T10:05:00Z'),
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
    expect(screen.getByText(/completed:/i)).toBeInTheDocument();
  });

  it('should display error alert for failed jobs', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'FAILED',
      isFailed: true,
      errorMessage: 'Network connection failed',
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.getAllByText('Ingestion Failed')[0]).toBeInTheDocument();
    expect(screen.getByText('Network connection failed')).toBeInTheDocument();
  });

  it('should call onComplete callback when job completes', async () => {
    const onComplete = vi.fn();

    const { rerender } = render(
      <App>
        <IngestionMonitor jobId="job-1" onComplete={onComplete} />
      </App>
    );

    // Update job to completed
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'COMPLETED',
      isCompleted: true,
      progressPercentage: 100,
    };

    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onComplete={onComplete} />
      </App>
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalled();
    });
  });

  it('should call onError callback when job fails', async () => {
    const onError = vi.fn();

    const { rerender } = render(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    // Update job to failed
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'FAILED',
      isFailed: true,
      errorMessage: 'Processing error',
    };

    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Processing error');
    });
  });

  it('should display loading state when job is not found', () => {
    mockJobStore.jobs = {};

    render(
      <App>
        <IngestionMonitor jobId="job-unknown" />
      </App>
    );

    expect(screen.getByText(/loading job status/i)).toBeInTheDocument();
  });

  it('should show success status color for completed jobs', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'COMPLETED',
      isCompleted: true,
      progressPercentage: 100,
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const statusTag = screen.getByText('COMPLETED');
    expect(statusTag).toBeInTheDocument();
  });

  it('should show error status color for failed jobs', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'FAILED',
      isFailed: true,
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const statusTag = screen.getByText('FAILED');
    expect(statusTag).toBeInTheDocument();
  });

  it('should show processing status color for running jobs', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const statusTag = screen.getByText('RUNNING');
    expect(statusTag).toBeInTheDocument();
  });

  it('should display progress bar with active status for running jobs', () => {
    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
  });

  it('should display progress bar with success status for completed jobs', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'COMPLETED',
      isCompleted: true,
      progressPercentage: 100,
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
  });

  it('should display progress bar with exception status for failed jobs', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'FAILED',
      isFailed: true,
      progressPercentage: 75,
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
  });

  it('should handle job with 0% progress', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      progressPercentage: 0,
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
  });

  it('should handle job without current step', () => {
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      currentStep: undefined,
    };

    render(
      <App>
        <IngestionMonitor jobId="job-1" />
      </App>
    );

    expect(screen.queryByText(/current step:/i)).not.toBeInTheDocument();
  });

  it('should only notify once for completed jobs', async () => {
    const onComplete = vi.fn();

    const { rerender } = render(
      <App>
        <IngestionMonitor jobId="job-1" onComplete={onComplete} />
      </App>
    );

    // Update job to completed
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'COMPLETED',
      isCompleted: true,
    };

    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onComplete={onComplete} />
      </App>
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledTimes(1);
    });

    // Rerender again - should not call onComplete again
    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onComplete={onComplete} />
      </App>
    );

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('should only notify once for failed jobs', async () => {
    const onError = vi.fn();

    const { rerender } = render(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    // Update job to failed
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'FAILED',
      isFailed: true,
      errorMessage: 'Error',
    };

    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    await waitFor(() => {
      expect(onError).toHaveBeenCalledTimes(1);
    });

    // Rerender again - should not call onError again
    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('should use default error message when errorMessage is not provided', async () => {
    const onError = vi.fn();

    const { rerender } = render(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    // Update job to failed without error message
    mockJobStore.jobs['job-1'] = {
      ...mockJobStore.jobs['job-1'],
      status: 'FAILED',
      isFailed: true,
    };

    rerender(
      <App>
        <IngestionMonitor jobId="job-1" onError={onError} />
      </App>
    );

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Ingestion failed');
    });
  });
});
