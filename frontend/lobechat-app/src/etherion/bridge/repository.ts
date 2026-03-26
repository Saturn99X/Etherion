import { getClient } from '@etherion/lib/apollo-client';
import { LIST_REPOSITORY_ASSETS } from '@etherion/lib/graphql-operations';

export interface RepositoryAsset {
  assetId: string;
  jobId?: string | null;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  gcsUri: string;
  createdAt: string;
  downloadUrl?: string | null;
  previewBase64?: string | null;
}

/**
 * Replay artifact type with specialized fields for transcript and trace.
 */
export interface ReplayArtifact extends RepositoryAsset {
  replayType: 'transcript' | 'trace';
}

interface ListRepositoryAssetsResponse {
  listRepositoryAssets: RepositoryAsset[];
}

export interface ListAssetsOptions {
  limit?: number;
  jobId?: string | null;
  includeDownload?: boolean;
}

export async function listAssets(options: ListAssetsOptions = {}): Promise<RepositoryAsset[]> {
  const { limit, jobId, includeDownload } = options;

  const safeLimit =
    typeof limit === 'number' && Number.isFinite(limit) && limit > 0
      ? Math.min(Math.floor(limit), 500)
      : 50;
  const safeJobId = jobId ?? null;

  const { data } = await getClient().query<ListRepositoryAssetsResponse>({
    query: LIST_REPOSITORY_ASSETS,
    variables: {
      limit: safeLimit,
      jobId: safeJobId,
      include_download: includeDownload ?? true,
    },
    fetchPolicy: 'network-only',
  });

  return data?.listRepositoryAssets ?? [];
}

export async function getAsset(assetId: string): Promise<RepositoryAsset | null> {
  const trimmed = (assetId ?? '').trim();
  if (!trimmed) {
    throw new Error('assetId is required');
  }

  const assets = await listAssets({ limit: 100, includeDownload: true });
  return assets.find((a) => a.assetId === trimmed) ?? null;
}

export async function getAssetPreview(assetId: string): Promise<string | null> {
  const asset = await getAsset(assetId);
  return asset?.previewBase64 ?? null;
}

// =============================================================================
// REPLAY ARTIFACT DETECTION (Phase D4)
// =============================================================================

/**
 * Known replay artifact filenames.
 */
const REPLAY_TRANSCRIPT_FILENAME = 'replay_transcript.md';
const REPLAY_TRACE_FILENAME = 'replay_trace.jsonl';

/**
 * Check if an asset is a replay artifact.
 */
export function isReplayArtifact(asset: RepositoryAsset): boolean {
  const filename = asset.filename?.toLowerCase() ?? '';
  return filename === REPLAY_TRANSCRIPT_FILENAME || filename === REPLAY_TRACE_FILENAME;
}

/**
 * Determine the replay type of an artifact.
 */
export function getReplayType(asset: RepositoryAsset): 'transcript' | 'trace' | null {
  const filename = asset.filename?.toLowerCase() ?? '';
  if (filename === REPLAY_TRANSCRIPT_FILENAME) return 'transcript';
  if (filename === REPLAY_TRACE_FILENAME) return 'trace';
  return null;
}

/**
 * List all replay artifacts for a specific job.
 */
export async function listReplayArtifacts(jobId: string): Promise<ReplayArtifact[]> {
  const normalizedJobId = (jobId ?? '').trim();
  if (!normalizedJobId) {
    throw new Error('jobId is required to list replay artifacts');
  }

  const assets = await listAssets({ jobId: normalizedJobId, includeDownload: true });

  return assets
    .filter(isReplayArtifact)
    .map((asset) => ({
      ...asset,
      replayType: getReplayType(asset)!,
    }));
}

/**
 * Get the replay transcript for a job (markdown content).
 * Returns the download URL and optionally fetches the content.
 */
export async function getReplayTranscript(jobId: string): Promise<{
  asset: ReplayArtifact | null;
  content: string | null;
}> {
  const artifacts = await listReplayArtifacts(jobId);
  const transcript = artifacts.find((a) => a.replayType === 'transcript') ?? null;

  if (!transcript) {
    return { asset: null, content: null };
  }

  // Try to fetch content if downloadUrl is available
  let content: string | null = null;
  if (transcript.downloadUrl) {
    try {
      const response = await fetch(transcript.downloadUrl);
      if (response.ok) {
        content = await response.text();
      }
    } catch (err) {
      console.warn('Failed to fetch replay transcript content:', err);
    }
  }

  return { asset: transcript, content };
}

/**
 * Get the replay trace JSONL for a job (download URL only — typically large file).
 */
export async function getReplayTrace(jobId: string): Promise<ReplayArtifact | null> {
  const artifacts = await listReplayArtifacts(jobId);
  return artifacts.find((a) => a.replayType === 'trace') ?? null;
}

/**
 * Check if a completed job has replay artifacts available.
 */
export async function hasReplayArtifacts(jobId: string): Promise<boolean> {
  try {
    const artifacts = await listReplayArtifacts(jobId);
    return artifacts.length > 0;
  } catch {
    return false;
  }
}
