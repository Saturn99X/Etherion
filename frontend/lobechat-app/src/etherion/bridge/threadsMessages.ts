import { getClient } from '@etherion/lib/apollo-client';
import { LIST_MESSAGES_QUERY } from '@etherion/lib/graphql-operations';
import { useThreadStore, type ChatMessage } from '@etherion/stores/useThreadStore';

interface ListMessagesItem {
  messageId: string;
  threadId: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  parentId?: string | null;
  branchId?: string | null;
  createdAt: string;
}

interface ListMessagesResponse {
  listMessages: ListMessagesItem[];
}

export async function loadThreadMessages(
  threadId: string,
  branchId?: string,
  limit?: number,
  offset?: number,
): Promise<ChatMessage[]> {
  const normalizedThreadId = (threadId ?? '').trim();
  if (!normalizedThreadId) {
    throw new Error('threadId is required to load messages');
  }

  const safeLimit =
    typeof limit === 'number' && Number.isFinite(limit) && limit > 0
      ? Math.floor(limit)
      : undefined;
  const safeOffset =
    typeof offset === 'number' && Number.isFinite(offset) && offset >= 0
      ? Math.floor(offset)
      : undefined;

  const { data } = await getClient().query<ListMessagesResponse>({
    query: LIST_MESSAGES_QUERY,
    variables: {
      thread_id: normalizedThreadId,
      branch_id: branchId ?? null,
      limit: safeLimit,
      offset: safeOffset,
    },
    fetchPolicy: 'network-only',
  });

  const items: ListMessagesItem[] = data?.listMessages ?? [];

  const messages: ChatMessage[] = items.map((m) => ({
    id: m.messageId,
    role: m.role,
    content: m.content,
    parentId: m.parentId ?? undefined,
    branchId: m.branchId ?? undefined,
    timestamp: m.createdAt,
    metadata: {},
  }));

  useThreadStore.setState((state) => {
    const existing = state.threads[normalizedThreadId] ?? [];
    const byId = new Map<string, ChatMessage>();

    for (const msg of existing) {
      byId.set(msg.id, msg);
    }
    for (const msg of messages) {
      byId.set(msg.id, msg);
    }

    const merged = Array.from(byId.values()).sort((a, b) =>
      a.timestamp.localeCompare(b.timestamp),
    );

    return {
      threads: {
        ...state.threads,
        [normalizedThreadId]: merged,
      },
    };
  });

  return messages;
}

