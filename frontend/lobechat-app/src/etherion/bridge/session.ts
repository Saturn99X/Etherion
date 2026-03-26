/**
 * Thread bridge for LobeChat — uses real backend Thread surfaces.
 *
 * NOTE: The Etherion backend currently does NOT have dedicated createThread/renameThread/deleteThread
 * mutations. Thread creation happens implicitly when executeGoal is called without a threadId.
 * This bridge reflects that constraint.
 */

import { getClient } from '@etherion/lib/apollo-client';
import { LIST_THREADS_QUERY, GET_THREAD_QUERY } from '@etherion/lib/graphql-operations';

export interface ThreadSummary {
  /** Real backend threadId (string) */
  id: string;
  title: string;
  teamId?: string;
  createdAt: string;
  lastActivityAt: string;
}

interface BackendThread {
  threadId: string;
  title: string | null;
  teamId: string | null;
  createdAt: string;
  lastActivityAt: string | null;
}

interface ListThreadsResponse {
  listThreads: BackendThread[];
}

interface GetThreadResponse {
  getThread: BackendThread | null;
}

/**
 * List all threads for the current tenant/user.
 */
export async function getThreads(limit?: number, offset?: number): Promise<ThreadSummary[]> {
  const safeLimit = typeof limit === 'number' && Number.isFinite(limit) && limit > 0
    ? Math.floor(limit)
    : undefined;
  const safeOffset = typeof offset === 'number' && Number.isFinite(offset) && offset >= 0
    ? Math.floor(offset)
    : undefined;

  const { data } = await getClient().query<ListThreadsResponse>({
    query: LIST_THREADS_QUERY,
    variables: { limit: safeLimit, offset: safeOffset },
    fetchPolicy: 'network-only',
  });

  const threads = data?.listThreads ?? [];

  return threads.map((t) => ({
    id: t.threadId,
    title: t.title || 'Untitled',
    teamId: t.teamId ?? undefined,
    createdAt: t.createdAt,
    lastActivityAt: t.lastActivityAt || t.createdAt,
  }));
}

/**
 * Get a single thread by its backend threadId.
 */
export async function getThread(threadId: string): Promise<ThreadSummary | null> {
  const normalizedId = (threadId ?? '').trim();
  if (!normalizedId) {
    return null;
  }

  const { data } = await getClient().query<GetThreadResponse>({
    query: GET_THREAD_QUERY,
    variables: { thread_id: normalizedId },
    fetchPolicy: 'network-only',
  });

  const t = data?.getThread;
  if (!t) return null;

  return {
    id: t.threadId,
    title: t.title || 'Untitled',
    teamId: t.teamId ?? undefined,
    createdAt: t.createdAt,
    lastActivityAt: t.lastActivityAt || t.createdAt,
  };
}

/**
 * Create a new thread.
 *
 * NOTE: The backend does NOT have a standalone createThread mutation.
 * New threads are created implicitly by calling executeGoal without a threadId.
 * The job's execution trace will emit a THREAD_CREATED event with the new threadId.
 *
 * This function throws an error to indicate the correct pattern.
 * Use sendGoal() without threadId to start a new conversation.
 */
export async function createThread(): Promise<never> {
  throw new Error(
    'createThread is not supported. To start a new conversation, call sendGoal() without ' +
    'a threadId. The backend will create a thread implicitly and emit THREAD_CREATED in the ' +
    'execution trace. Listen for that event to learn the new threadId.'
  );
}

/**
 * Rename a thread.
 *
 * NOTE: The backend does NOT currently support renaming threads.
 * This function is a no-op placeholder.
 */
export async function renameThread(_threadId: string, _newTitle: string): Promise<void> {
  console.warn('renameThread is not supported by the backend. Thread titles are read-only.');
}

/**
 * Delete a thread.
 *
 * NOTE: The backend does NOT currently support deleting threads.
 * This function is a no-op placeholder.
 */
export async function deleteThread(_threadId: string): Promise<void> {
  console.warn('deleteThread is not supported by the backend.');
}
