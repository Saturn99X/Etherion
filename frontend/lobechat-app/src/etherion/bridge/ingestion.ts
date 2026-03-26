/**
 * Ingestion Bridge (Phase D5)
 *
 * Handles async ingestion flows with the 202 + poll pattern.
 * The backend returns 202 Accepted quickly and performs heavy work asynchronously.
 */

export interface IngestJobResponse {
    jobId: string;
    gcsUri: string;
    message?: string;
}

export interface IngestStatusResponse {
    jobId: string;
    stage: IngestStage;
    substage?: string;
    progress?: number;
    error?: string;
    completedAt?: string;
}

export type IngestStage =
    | 'INIT'
    | 'UPLOADING'
    | 'PARSING'
    | 'CHUNKING'
    | 'EMBEDDING'
    | 'INDEXING'
    | 'COMPLETED'
    | 'FAILED';

/**
 * Start an ingestion job. Returns immediately with job_id.
 * The actual ingestion runs asynchronously on the backend.
 *
 * @param file - File to ingest
 * @param options - Optional parameters
 * @returns Job ID and GCS URI for tracking
 */
export async function startIngestion(
    file: File,
    options: {
        metadata?: Record<string, string>;
        authToken?: string;
    } = {}
): Promise<IngestJobResponse> {
    const formData = new FormData();
    formData.append('file', file);

    if (options.metadata) {
        formData.append('metadata', JSON.stringify(options.metadata));
    }

    const headers: Record<string, string> = {};
    const token = options.authToken ?? getAuthToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch('/webhook/admin/ingest-bytes', {
        method: 'POST',
        headers,
        body: formData,
    });

    if (response.status === 202) {
        const data = await response.json();
        return {
            jobId: data.job_id,
            gcsUri: data.gcs_uri,
            message: data.message,
        };
    }

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Ingestion failed: ${response.status} ${errorText}`);
    }

    // Unexpected success status (should be 202)
    const data = await response.json();
    return {
        jobId: data.job_id,
        gcsUri: data.gcs_uri,
        message: data.message,
    };
}

/**
 * Poll ingestion status for a job.
 *
 * @param jobId - The job ID returned from startIngestion
 * @returns Current ingestion status
 */
export async function getIngestionStatus(jobId: string): Promise<IngestStatusResponse> {
    const normalizedJobId = (jobId ?? '').trim();
    if (!normalizedJobId) {
        throw new Error('jobId is required to check ingestion status');
    }

    const response = await fetch(`/webhook/admin/ingest-status/${normalizedJobId}`, {
        method: 'GET',
        headers: {
            Authorization: `Bearer ${getAuthToken()}`,
        },
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to get ingestion status: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    return {
        jobId: data.job_id ?? normalizedJobId,
        stage: data.stage ?? 'INIT',
        substage: data.substage,
        progress: data.progress,
        error: data.error,
        completedAt: data.completed_at,
    };
}

/**
 * Check if ingestion is complete (success or failure).
 */
export function isIngestionComplete(status: IngestStatusResponse): boolean {
    return status.stage === 'COMPLETED' || status.stage === 'FAILED';
}

/**
 * Check if ingestion failed.
 */
export function isIngestionFailed(status: IngestStatusResponse): boolean {
    return status.stage === 'FAILED';
}

/**
 * Poll ingestion status with callbacks.
 * Implements the 202 + poll pattern with a time budget.
 *
 * @param jobId - Job ID to poll
 * @param options - Polling options
 * @returns Final status when complete, or latest status if timed out
 */
export async function pollIngestionStatus(
    jobId: string,
    options: {
        intervalMs?: number;
        timeBudgetMs?: number;
        onProgress?: (status: IngestStatusResponse) => void;
        onComplete?: (status: IngestStatusResponse) => void;
        onError?: (error: Error) => void;
        onTimeout?: (status: IngestStatusResponse) => void;
    } = {}
): Promise<IngestStatusResponse> {
    const {
        intervalMs = 2000,
        timeBudgetMs = 120000, // 2 minute default budget
        onProgress,
        onComplete,
        onError,
        onTimeout,
    } = options;

    const startTime = Date.now();
    let lastStatus: IngestStatusResponse | null = null;

    const poll = async (): Promise<IngestStatusResponse> => {
        try {
            const status = await getIngestionStatus(jobId);
            lastStatus = status;
            onProgress?.(status);

            if (isIngestionComplete(status)) {
                if (isIngestionFailed(status)) {
                    const err = new Error(status.error || 'Ingestion failed');
                    onError?.(err);
                } else {
                    onComplete?.(status);
                }
                return status;
            }

            // Check time budget
            const elapsed = Date.now() - startTime;
            if (elapsed >= timeBudgetMs) {
                onTimeout?.(status);
                return status;
            }

            // Wait and poll again
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
            return poll();
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            onError?.(err);
            throw err;
        }
    };

    return poll();
}

/**
 * Convenience function to ingest and wait for completion.
 * Combines startIngestion + pollIngestionStatus.
 */
export async function ingestAndWait(
    file: File,
    options: {
        metadata?: Record<string, string>;
        timeBudgetMs?: number;
        onProgress?: (status: IngestStatusResponse) => void;
    } = {}
): Promise<{
    jobId: string;
    status: IngestStatusResponse;
    timedOut: boolean;
}> {
    const { jobId } = await startIngestion(file, { metadata: options.metadata });

    let timedOut = false;

    const status = await pollIngestionStatus(jobId, {
        timeBudgetMs: options.timeBudgetMs ?? 120000,
        onProgress: options.onProgress,
        onTimeout: () => {
            timedOut = true;
        },
    });

    return { jobId, status, timedOut };
}

/**
 * Helper to get auth token from localStorage.
 */
function getAuthToken(): string {
    if (typeof window !== 'undefined') {
        return window.localStorage.getItem('auth_token') || '';
    }
    return '';
}
