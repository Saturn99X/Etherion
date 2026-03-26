import { create } from 'zustand';
import { useThreadStore } from '@/lib/stores/useThreadStore';

export interface JobStatusUpdate {
  job_id: string;
  status: string;
  timestamp: string;
  message?: string;
  progress_percentage?: number;
  current_step_description?: string;
  error_message?: string;
  additional_data?: any;
}

interface Job {
  id: string;
  status: string;
  progressPercentage?: number;
  currentStep?: string;
  errorMessage?: string;
  isCompleted: boolean;
  isFailed: boolean;
  createdAt: Date;
  completedAt?: Date;
  archivedTrace?: string;
  threadId?: string;
}

interface JobStore {
  jobs: Record<string, Job>;
  subscriptions: Record<string, any>;

  // Actions
  addJob: (jobId: string, threadId?: string) => void;
  updateJob: (jobId: string, update: Partial<JobStatusUpdate>) => void;
  markJobCompleted: (jobId: string) => void;
  markJobFailed: (jobId: string, errorMessage?: string) => void;
  setArchivedTrace: (jobId: string, trace: string) => void;
  removeJob: (jobId: string) => void;
  subscribeToJob: (jobId: string) => void;
  unsubscribeFromJob: (jobId: string) => void;
  clearAllJobs: () => void;
}

export const useJobStore = create<JobStore>((set, get) => ({
  jobs: {},
  subscriptions: {},

  addJob: (jobId: string, threadId?: string) => {
    set((state) => ({
      jobs: {
        ...state.jobs,
        [jobId]: {
          id: jobId,
          status: 'QUEUED',
          progressPercentage: 0,
          currentStep: 'Initializing...',
          isCompleted: false,
          isFailed: false,
          createdAt: new Date(),
          threadId,
        },
      },
    }));
  },

  updateJob: (jobId: string, update: Partial<JobStatusUpdate>) => {
    set((state) => {
      const existingJob = state.jobs[jobId];
      if (!existingJob) return state;

      const nextStatus = ((update.status || existingJob.status || '') as string).toString().toUpperCase();

      const updatedJob: Job = {
        ...existingJob,
        status: nextStatus || existingJob.status,
        progressPercentage: update.progress_percentage ?? existingJob.progressPercentage,
        currentStep: update.current_step_description || existingJob.currentStep,
        errorMessage: update.error_message || existingJob.errorMessage,
        isCompleted: nextStatus === 'COMPLETED',
        isFailed: nextStatus === 'FAILED' || nextStatus === 'ERROR',
        completedAt: nextStatus === 'COMPLETED' ? new Date() : existingJob.completedAt,
      };

      return {
        jobs: {
          ...state.jobs,
          [jobId]: updatedJob,
        },
      };
    });
  },

  markJobCompleted: (jobId: string) => {
    set((state) => {
      const existingJob = state.jobs[jobId];
      if (!existingJob) return state;

      return {
        jobs: {
          ...state.jobs,
          [jobId]: {
            ...existingJob,
            isCompleted: true,
            isFailed: false,
            status: 'COMPLETED',
            completedAt: new Date(),
          },
        },
      };
    });
  },

  markJobFailed: (jobId: string, errorMessage?: string) => {
    set((state) => {
      const existingJob = state.jobs[jobId];
      if (!existingJob) return state;

      return {
        jobs: {
          ...state.jobs,
          [jobId]: {
            ...existingJob,
            isCompleted: false,
            isFailed: true,
            status: 'FAILED',
            errorMessage: errorMessage || 'Job failed',
          },
        },
      };
    });
  },

  setArchivedTrace: (jobId: string, trace: string) => {
    set((state) => {
      const existingJob = state.jobs[jobId];
      if (!existingJob) return state;

      return {
        jobs: {
          ...state.jobs,
          [jobId]: {
            ...existingJob,
            archivedTrace: trace,
          },
        },
      };
    });
  },

  removeJob: (jobId: string) => {
    set((state) => {
      const { [jobId]: removed, ...remainingJobs } = state.jobs;
      return { jobs: remainingJobs };
    });
  },

  subscribeToJob: (jobId: string) => {
    const state = get();
    if (state.subscriptions[jobId]) return; // already subscribed

    try {
      // Lazy import to avoid SSR issues
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { apolloClient } = require('@/components/apollo-provider');
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { SUBSCRIBE_TO_JOB_STATUS, SUBSCRIBE_TO_EXECUTION_TRACE } = require('@/lib/graphql-operations');

      const sub1 = apolloClient.subscribe({
        query: SUBSCRIBE_TO_JOB_STATUS,
        variables: { job_id: jobId },
      }).subscribe({
        next: ({ data }: any) => {
          if (data?.subscribeToJobStatus) {
            get().updateJob(jobId, data.subscribeToJobStatus);
          }
        },
        error: (err: any) => console.error('Job status subscription error:', err),
      });

      const sub2 = apolloClient.subscribe({
        query: SUBSCRIBE_TO_EXECUTION_TRACE,
        variables: { job_id: jobId },
      }).subscribe({
        next: ({ data }: any) => {
          if (data?.subscribeToExecutionTrace) {
            const evt = data.subscribeToExecutionTrace;
            get().updateJob(jobId, {
              status: evt.status,
              current_step_description: evt.current_step_description,
            } as any);

            // Artifact mapping: detect asset/preview events and attach to initiating assistant message
            try {
              const add = evt.additional_data || {};
              const artifacts: Array<{ kind: 'html'|'svg'|'doc'|'code'; content: string; title?: string }> = [];
              // Heuristics based on backend event payloads
              if (add) {
                // HTML content
                if (typeof add.html === 'string' && add.html.trim().length > 0) {
                  artifacts.push({ kind: 'html', content: add.html, title: add.title || add.filename });
                }
                // SVG
                if (typeof add.svg === 'string' && add.svg.trim().length > 0) {
                  artifacts.push({ kind: 'svg', content: add.svg, title: add.title || add.filename });
                } else if (typeof add.previewBase64 === 'string' && /svg/.test(add.mime_type || '')) {
                  try {
                    const svg = atob((add.previewBase64 || '').split(',').pop() || '');
                    if (svg) artifacts.push({ kind: 'svg', content: svg, title: add.title || add.filename });
                  } catch {}
                }
                // Code
                if (typeof add.code === 'string' && add.code.trim().length > 0) {
                  artifacts.push({ kind: 'code', content: add.code, title: add.title || add.filename || add.language });
                }
                // Doc/text
                if (typeof add.text === 'string' && add.text.trim().length > 0) {
                  artifacts.push({ kind: 'doc', content: add.text, title: add.title || add.filename });
                } else if (typeof add.summary === 'string' && add.summary.trim().length > 0) {
                  artifacts.push({ kind: 'doc', content: add.summary, title: add.title || add.filename });
                }
              }

              if (artifacts.length > 0) {
                const threadId = get().jobs[jobId]?.threadId;
                if (threadId) {
                  const ts = useThreadStore.getState();
                  const msgs = ts.threads[threadId] || [];
                  const target = msgs.find((m: any) => m?.metadata?.toolExecId === jobId);
                  if (target) {
                    const existing = (target.metadata?.artifacts as any[]) || [];
                    ts.setMessageMetadata(threadId, target.id, {
                      artifacts: [...existing, ...artifacts],
                      showArtifacts: true,
                    });
                  }
                }
              }
            } catch (e) {
              // Best-effort; do not crash subscription
              console.warn('Artifact mapping failed for job', jobId, e);
            }
          }
        },
        error: (err: any) => console.error('Execution trace subscription error:', err),
      });

      set((s) => ({
        subscriptions: {
          ...s.subscriptions,
          [jobId]: [sub1, sub2],
        },
      }));
    } catch (e) {
      console.error('Failed to subscribe to job:', jobId, e);
    }
  },

  unsubscribeFromJob: (jobId: string) => {
    set((s) => {
      const subs = s.subscriptions[jobId];
      if (subs && Array.isArray(subs)) {
        try {
          subs.forEach((sub) => sub?.unsubscribe?.());
        } catch (e) {
          console.error('Error unsubscribing:', e);
        }
      }
      const { [jobId]: _rm, ...rest } = s.subscriptions;
      return { subscriptions: rest };
    });
  },

  clearAllJobs: () => {
    set({ jobs: {}, subscriptions: {} });
  },
}));
