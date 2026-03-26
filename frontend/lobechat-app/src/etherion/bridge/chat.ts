import { nanoid } from 'nanoid';

import { GoalService, type GoalInput, type JobResponse } from '@etherion/lib/services/goal-service';
import { useAuthStore } from '@etherion/stores/auth-store';
import { useChatAttachmentsStore } from '@etherion/stores/chat-attachments-store';
import { useThreadPrefStore } from '@etherion/stores/thread-pref-store';
import { useThreadStore, type ChatMessage } from '@etherion/stores/useThreadStore';
import { useJobStore } from '@etherion/stores/job-store';
import { fetchSSE, type FetchSSEOptions } from '@etherion/lib/lobe/streaming';
import type { UploadFileItem } from '@/types/files/upload';

export interface SendGoalOptions {
  threadId: string;
  branchId?: string;
  text: string;
  attachments?: UploadFileItem[];
  context?: string;
  outputFormatInstructions?: string;
  teamId?: string;
  provider?: string;
  model?: string;
  planMode?: boolean;
  searchForce?: boolean;
}

export interface SendGoalResult {
  job: JobResponse;
  /** ID of the optimistic assistant message created for streaming */
  assistantMessageId: string;
}

export interface SubscribeToStreamHandlers {
  onTextDelta?: (delta: string) => void;
  onFinish?: FetchSSEOptions['onFinish'];
  onError?: FetchSSEOptions['onErrorHandle'];
}

/**
 * Fire-and-forget goal execution entrypoint used by LobeChat chat flows.
 * - Ensures user is authenticated.
 * - Binds the goal to the current thread/branch and thread preferences.
 * - Creates an optimistic assistant message to stream into.
 * - Starts job tracking via useJobStore.
 */
export async function sendGoal(options: SendGoalOptions): Promise<SendGoalResult> {
  const {
    threadId,
    branchId,
    text,
    context,
    outputFormatInstructions,
    teamId,
    provider,
    model,
    planMode,
    searchForce,
  } = options;

  const auth = useAuthStore.getState();
  if (!auth.user) throw new Error('User must be authenticated to send a goal');

  const threadPrefStore = useThreadPrefStore.getState();
  const prefs = threadPrefStore.getPrefs(threadId, branchId);

  const goalInput: GoalInput = {
    goal: text,
    context,
    output_format_instructions: outputFormatInstructions,
    agentTeamId: teamId,
    plan_mode: planMode,
    search_force: searchForce ?? threadPrefStore.searchForce[threadId] ?? false,
    provider,
    model,
    threadId,
  };

  const job = await GoalService.executeGoal(goalInput);

  // Attachments are currently tracked via useChatAttachmentsStore; we clear them
  // after a successful goal submission so the next send starts clean for this
  // thread/branch. The actual upload/attachment semantics are handled by
  // Etherion repository tooling in other bridges.
  const attachmentsStore = useChatAttachmentsStore.getState();
  const existingAttachments = attachmentsStore.getItems(threadId, branchId);
  if (existingAttachments.length > 0) {
    attachmentsStore.clear(threadId, branchId);
  }

  const threadStore = useThreadStore.getState();
  const assistantMessageId = nanoid();

  const assistantMessage: ChatMessage = {
    id: assistantMessageId,
    role: 'assistant',
    content: '',
    branchId,
    timestamp: new Date().toISOString(),
    metadata: {
      toolExecId: job.job_id,
      showCot: false,
      showArtifacts: false,
    },
  };

  threadStore.addMessage(threadId, assistantMessage);

  const jobStore = useJobStore.getState();
  jobStore.addJob(job.job_id, threadId);
  jobStore.subscribeToJob(job.job_id);

  return { job, assistantMessageId };
}

/**
 * Low-level streaming helper that wires Etherion's SSE endpoint into
 * LobeChat-style callbacks while still updating Etherion stores.
 */
export function subscribeToStream(jobId: string, url: string, options: FetchSSEOptions = {}): AbortController {
  const controller = new AbortController();

  fetchSSE(url, {
    ...options,
    signal: controller.signal,
  }).catch((err) => {
    options.onErrorHandle?.(err as any);
  });

  return controller;
}

/**
 * Get the SSE streaming URL for a job.
 * Uses /api/stream which is the Next.js proxy that forwards to ORCHESTRATOR_SSE_URL.
 */
function getSSEUrl(): string {
  // In browser, check window.ENV first, then fall back to env
  if (typeof window !== 'undefined') {
    const envUrl = (window as any).ENV?.NEXT_PUBLIC_CHAT_SSE_URL;
    if (envUrl) return envUrl;
  }
  // Fall back to environment variable or default
  return process.env.NEXT_PUBLIC_CHAT_SSE_URL || '/api/stream';
}

export interface SendGoalAndStreamResult {
  job: JobResponse;
  assistantMessageId: string;
  /** Abort controller to cancel the stream */
  streamController: AbortController;
}

export interface SendGoalAndStreamOptions extends SendGoalOptions {
  /** Callbacks for streaming events */
  onTextDelta?: (delta: string, fullText: string) => void;
  onReasoningDelta?: (delta: string) => void;
  onToolCalls?: (toolCalls: any[]) => void;
  onFinish?: FetchSSEOptions['onFinish'];
  onError?: FetchSSEOptions['onErrorHandle'];
}

/**
 * Combined goal execution + SSE streaming entrypoint.
 *
 * This function:
 * 1. Calls sendGoal() to dispatch the goal and create an optimistic assistant message.
 * 2. Opens an SSE stream to receive token deltas.
 * 3. Applies deltas into the optimistic assistant message via useThreadStore.
 * 4. Returns an abort controller so the caller can cancel the stream.
 *
 * Use this as the primary send path in LobeChat chat flows for proper streaming.
 */
export async function sendGoalAndStream(options: SendGoalAndStreamOptions): Promise<SendGoalAndStreamResult> {
  const { onTextDelta, onReasoningDelta, onToolCalls, onFinish, onError, ...sendOptions } = options;

  // Step 1: Execute the goal and create optimistic message
  const { job, assistantMessageId } = await sendGoal(sendOptions);

  const threadId = sendOptions.threadId;
  const threadStore = useThreadStore.getState();

  let accumulatedText = '';

  // Step 2: Open SSE stream
  const sseUrl = getSSEUrl();
  const streamController = new AbortController();

  // POST to the SSE endpoint with job_id in the body
  fetchSSE(sseUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAuthToken()}`,
    },
    body: JSON.stringify({ job_id: job.job_id }),
    signal: streamController.signal,

    onMessageHandle: (chunk) => {
      switch (chunk.type) {
        case 'text': {
          // Accumulate text and update the assistant message
          accumulatedText += chunk.text;
          threadStore.updateMessageContent(threadId, assistantMessageId, accumulatedText);
          onTextDelta?.(chunk.text, accumulatedText);
          break;
        }
        case 'reasoning': {
          // Store reasoning in message metadata
          const currentMsg = threadStore.threads[threadId]?.find((m) => m.id === assistantMessageId);
          const existingCot = currentMsg?.metadata?.cot || '';
          const newCot = existingCot + (chunk.text || '');
          threadStore.setMessageMetadata(threadId, assistantMessageId, { cot: newCot });
          onReasoningDelta?.(chunk.text || '');
          break;
        }
        case 'tool_calls': {
          // Store tool calls in metadata
          threadStore.setMessageMetadata(threadId, assistantMessageId, {
            toolCalls: chunk.tool_calls,
          });
          onToolCalls?.(chunk.tool_calls);
          break;
        }
        // Other chunk types (grounding, usage, speed, base64_image) can be handled as needed
      }
    },

    onErrorHandle: (error) => {
      console.error('SSE stream error:', error);
      onError?.(error);
      // Mark job as failed in UI
      useJobStore.getState().markJobFailed(job.job_id, error?.message || 'Stream error');
    },

    onFinish: async (text, context) => {
      // Ensure final text is applied
      if (text && text !== accumulatedText) {
        threadStore.updateMessageContent(threadId, assistantMessageId, text);
      }
      // Store final reasoning if present
      if (context.reasoning?.content) {
        threadStore.setMessageMetadata(threadId, assistantMessageId, {
          cot: context.reasoning.content,
        });
      }
      await onFinish?.(text, context);
    },

    onAbort: async () => {
      // User cancelled the stream
      console.log('SSE stream aborted by user');
    },
  }).catch((err) => {
    console.error('SSE fetch error:', err);
    onError?.(err as any);
  });

  return { job, assistantMessageId, streamController };
}

/**
 * Helper to get the auth token from localStorage.
 */
function getAuthToken(): string {
  if (typeof window !== 'undefined') {
    return window.localStorage.getItem('auth_token') || '';
  }
  return '';
}
