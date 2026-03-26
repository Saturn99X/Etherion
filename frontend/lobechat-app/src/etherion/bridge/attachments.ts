import { useChatAttachmentsStore } from '@etherion/stores/chat-attachments-store';
import type { UploadFileItem } from '@/types/files/upload';

export type { UploadFileItem } from '@/types/files/upload';

/**
 * High-level attachment operations for LobeChat UI.
 *
 * These functions scope attachments per thread/branch using the same keying
 * strategy as the underlying store. They do not implement upload semantics;
 * they only manage local attachment state.
 */

export async function addFiles(
  threadId: string,
  files: File[],
  branchId?: string,
): Promise<void> {
  if (!threadId) throw new Error('threadId is required to add attachments');
  if (!files || files.length === 0) return;

  const store = useChatAttachmentsStore.getState();
  await store.addFiles(threadId, files, branchId);
}

export function removeAttachment(
  threadId: string,
  attachmentId: string,
  branchId?: string,
): void {
  if (!threadId) throw new Error('threadId is required to remove attachments');
  if (!attachmentId) return;

  const store = useChatAttachmentsStore.getState();
  store.remove(threadId, attachmentId, branchId);
}

export function clearAttachments(threadId: string, branchId?: string): void {
  if (!threadId) return;

  const store = useChatAttachmentsStore.getState();
  store.clear(threadId, branchId);
}

export function listAttachments(
  threadId: string,
  branchId?: string,
): UploadFileItem[] {
  if (!threadId) return [];

  const store = useChatAttachmentsStore.getState();
  return store.getItems(threadId, branchId);
}
