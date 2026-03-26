import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useJobStore } from '../job-store';

// Mock apollo client and graphql operations
vi.mock('@etherion/components/apollo-provider', () => ({
    apolloClient: {
        subscribe: vi.fn(() => ({
            subscribe: vi.fn(),
        })),
    },
}));

vi.mock('@etherion/lib/graphql-operations', () => ({
    SUBSCRIBE_TO_JOB_STATUS: 'SUBSCRIBE_TO_JOB_STATUS',
    SUBSCRIBE_TO_EXECUTION_TRACE: 'SUBSCRIBE_TO_EXECUTION_TRACE',
}));

describe('useJobStore', () => {
    beforeEach(() => {
        useJobStore.getState().clearAllJobs();
    });

    it('addJob initializes a job with an empty executionTrace', () => {
        const store = useJobStore.getState();
        store.addJob('job-1', 'thread-1');

        const job = useJobStore.getState().jobs['job-1'];
        expect(job).toBeDefined();
        expect(job.executionTrace).toEqual([]);
        expect(job.threadId).toBe('thread-1');
    });

    it('addExecutionStep appends a new step to the trace', () => {
        const store = useJobStore.getState();
        store.addJob('job-1');

        const step = {
            title: 'Running',
            summary: 'Searching for info',
            status: 'running' as const,
            timestamp: '2024-01-01T00:00:00Z',
        };

        store.addExecutionStep('job-1', step);

        const job = useJobStore.getState().jobs['job-1'];
        expect(job.executionTrace).toHaveLength(1);
        expect(job.executionTrace[0]).toEqual(step);
    });

    it('addExecutionStep avoids duplicate steps based on timestamp and title', () => {
        const store = useJobStore.getState();
        store.addJob('job-1');

        const step = {
            title: 'Running',
            summary: 'Searching for info',
            status: 'running' as const,
            timestamp: '2024-01-01T00:00:00Z',
        };

        store.addExecutionStep('job-1', step);
        store.addExecutionStep('job-1', step); // Duplicate

        const job = useJobStore.getState().jobs['job-1'];
        expect(job.executionTrace).toHaveLength(1);
    });

    it('updateJob handles PENDING_APPROVAL status and sets isPendingApproval', () => {
        const store = useJobStore.getState();
        store.addJob('job-1');

        store.updateJob('job-1', { status: 'PENDING_APPROVAL' });

        const job = useJobStore.getState().jobs['job-1'];
        expect(job.status).toBe('PENDING_APPROVAL');
        expect(job.isPendingApproval).toBe(true);
    });
});
