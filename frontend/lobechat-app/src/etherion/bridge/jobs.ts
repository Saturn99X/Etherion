import { GoalService } from '@etherion/lib/services/goal-service';
import { useJobStore } from '@etherion/stores/job-store';
import { hasReplayArtifacts, listReplayArtifacts, getReplayTranscript, getReplayTrace, type ReplayArtifact } from './repository';

interface JobSummary {
	id: string;
	status: string;
	progressPercentage?: number;
	currentStep?: string;
	errorMessage?: string;
	isCompleted: boolean;
	isFailed: boolean;
	isPendingApproval: boolean;
	createdAt: Date;
	completedAt?: Date;
	archivedTrace?: string;
	threadId?: string;
}

interface JobStatusHandlers {
	onChange?: (job: JobSummary | null) => void;
}

const jobStatusSubscriptions: Record<string, () => void> = {};

export function getJobSummary(jobId: string): JobSummary | null {
	const job = useJobStore.getState().jobs[jobId];
	if (!job) return null;
	return {
		...job,
		isPendingApproval: job.isPendingApproval ?? false,
	};
}

// Backwards‑compatible alias for any early callers.
export function getJob(jobId: string) {
	return getJobSummary(jobId);
}

export async function getArchivedTrace(jobId: string): Promise<string | null> {
	return GoalService.getArchivedTraceSummary(jobId);
}

// Backwards‑compatible alias.
export async function getJobArchivedTrace(jobId: string): Promise<string | null> {
	return getArchivedTrace(jobId);
}

export function listenToJobStatus(jobId: string, handlers: JobStatusHandlers = {}): void {
	const storeApi = useJobStore;
	// Ensure GraphQL subscriptions are active for this job
	storeApi.getState().subscribeToJob(jobId);

	// Tear down any existing listener for this jobId first
	if (jobStatusSubscriptions[jobId]) {
		jobStatusSubscriptions[jobId]!();
	}

	const unsubscribe = storeApi.subscribe((state, prevState) => {
		const current = (state.jobs && state.jobs[jobId]) || null;
		const prev = (prevState && prevState.jobs && prevState.jobs[jobId]) || null;
		if (current === prev) return;
		try {
			handlers.onChange?.(current ? { ...current, isPendingApproval: current.isPendingApproval ?? false } : null);
		} catch {
			// UI handlers should never break the store subscription
		}
	});

	jobStatusSubscriptions[jobId] = unsubscribe;
}

export function stopListening(jobId: string): void {
	const state = useJobStore.getState();
	state.unsubscribeFromJob(jobId);

	const unsubscribe = jobStatusSubscriptions[jobId];
	if (unsubscribe) {
		try {
			unsubscribe();
		} finally {
			delete jobStatusSubscriptions[jobId];
		}
	}
}

// Backwards‑compatible alias.
export function stopListeningToJobStatus(jobId: string): void {
	stopListening(jobId);
}

export async function cancelJob(jobId: string): Promise<boolean> {
	return GoalService.cancelJob(jobId);
}

// =============================================================================
// REPLAY ARTIFACT INTEGRATION (Phase D4)
// =============================================================================

/**
 * Check if a completed job has replay artifacts available.
 * Re-export from repository bridge for convenience.
 */
export { hasReplayArtifacts, listReplayArtifacts, getReplayTranscript, getReplayTrace };
export type { ReplayArtifact };

/**
 * Get all replay artifacts for a job (convenience wrapper).
 */
export async function getJobReplayArtifacts(jobId: string): Promise<{
	hasReplay: boolean;
	transcript: ReplayArtifact | null;
	trace: ReplayArtifact | null;
}> {
	const normalizedJobId = (jobId ?? '').trim();
	if (!normalizedJobId) {
		return { hasReplay: false, transcript: null, trace: null };
	}

	try {
		const artifacts = await listReplayArtifacts(normalizedJobId);
		const transcript = artifacts.find((a) => a.replayType === 'transcript') ?? null;
		const trace = artifacts.find((a) => a.replayType === 'trace') ?? null;
		return {
			hasReplay: artifacts.length > 0,
			transcript,
			trace,
		};
	} catch {
		return { hasReplay: false, transcript: null, trace: null };
	}
}
