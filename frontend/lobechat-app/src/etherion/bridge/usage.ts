import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_JOB_HISTORY_QUERY,
  GET_JOB_DETAILS_QUERY,
} from '@etherion/lib/graphql-operations';

interface JobHistoryJob {
  id: string;
  goal: string;
  status: string;
  createdAt: string;
  completedAt?: string | null;
  duration: string;
  totalCost: string;
  modelUsed?: string | null;
  tokenCount?: number | null;
  successRate?: number | null;
}

interface JobHistoryResponse {
  getJobHistory: {
    jobs: JobHistoryJob[];
    totalCount: number;
  };
}

interface JobDetailsOutputData {
  total_cost?: number | string | null;
  [key: string]: unknown;
}

interface JobDetailsResponse {
  getJobDetails: {
    output_data?: JobDetailsOutputData | null;
  } | null;
}

export interface JobUsageItem {
  id: string;
  goal: string;
  status: string;
  createdAt: string;
  completedAt?: string | null;
  duration: string;
  /** Display string returned by backend, e.g. "$12.50". */
  totalCostDisplay: string;
  /** Parsed numeric USD cost derived from totalCostDisplay. */
  totalCostUsd: number;
  modelUsed?: string | null;
  tokenCount?: number | null;
  successRate?: number | null;
}

export interface UsageSummaryFilter {
  limit?: number;
  offset?: number;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
}

export interface UsageSummary {
  totalJobs: number;
  totalCostUsd: number;
  jobs: JobUsageItem[];
}

function parseUsdFromDisplay(value: string | null | undefined): number {
  if (!value) return 0;
  const cleaned = value.replace(/[^0-9.+-]+/g, '');
  const parsed = Number.parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Bridge 16 – Usage & Cost
 *
 * getUsageSummary: derives a simple usage view from Etherion's getJobHistory
 * GraphQL endpoint. It does not compute pricing; it only aggregates the
 * backend-provided totalCost per job.
 */
export async function getUsageSummary(filter: UsageSummaryFilter = {}): Promise<UsageSummary> {
  const { limit = 50, offset = 0, status, dateFrom, dateTo } = filter;

  const { data } = await getClient().query<JobHistoryResponse>({
    query: GET_JOB_HISTORY_QUERY,
    variables: {
      limit,
      offset,
      status: status ?? null,
      date_from: dateFrom ?? null,
      date_to: dateTo ?? null,
    },
    fetchPolicy: 'network-only',
  });

  const history = data.getJobHistory;
  const jobs: JobUsageItem[] = history.jobs.map((job) => {
    const costUsd = parseUsdFromDisplay(job.totalCost);
    return {
      id: job.id,
      goal: job.goal,
      status: job.status,
      createdAt: job.createdAt,
      completedAt: job.completedAt ?? null,
      duration: job.duration,
      totalCostDisplay: job.totalCost,
      totalCostUsd: costUsd,
      modelUsed: job.modelUsed ?? null,
      tokenCount: job.tokenCount ?? null,
      successRate: job.successRate ?? null,
    };
  });

  const totalCostUsd = jobs.reduce((sum, j) => sum + j.totalCostUsd, 0);

  return {
    totalJobs: history.totalCount,
    totalCostUsd,
    jobs,
  };
}

/**
 * Return the numeric total_cost for a specific job, based on
 * getJobDetails.output_data.total_cost when present.
 */
export async function getJobCost(jobId: string): Promise<number> {
  if (!jobId) throw new Error('jobId is required');

  const { data } = await getClient().query<JobDetailsResponse>({
    query: GET_JOB_DETAILS_QUERY,
    variables: { job_id: jobId },
    fetchPolicy: 'network-only',
  });

  const total = data.getJobDetails?.output_data?.total_cost;

  if (typeof total === 'number') {
    return total;
  }
  if (typeof total === 'string') {
    return parseUsdFromDisplay(total);
  }

  return 0;
}

/**
 * Derive a simple usage breakdown by model/provider based on job history.
 *
 * This groups jobs by modelUsed and sums backend-provided totalCost, without
 * re-implementing pricing logic.
 */
export async function getUsageByProvider(filter: UsageSummaryFilter = {}): Promise<
  Array<{ model: string; totalCostUsd: number; jobCount: number }>
> {
  const summary = await getUsageSummary(filter);

  const byModel = new Map<string, { totalCostUsd: number; jobCount: number }>();

  for (const job of summary.jobs) {
    const key = job.modelUsed || 'unknown';
    const existing = byModel.get(key) || { totalCostUsd: 0, jobCount: 0 };
    existing.totalCostUsd += job.totalCostUsd;
    existing.jobCount += 1;
    byModel.set(key, existing);
  }

  return Array.from(byModel.entries()).map(([model, agg]) => ({
    model,
    totalCostUsd: agg.totalCostUsd,
    jobCount: agg.jobCount,
  }));
}
