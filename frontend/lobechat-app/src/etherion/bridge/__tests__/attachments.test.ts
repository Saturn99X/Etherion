import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  addFiles,
  clearAttachments,
  listAttachments,
  removeAttachment,
} from '../attachments';

const state: any = {
  addFiles: vi.fn(),
  remove: vi.fn(),
  clear: vi.fn(),
  getItems: vi.fn(),
};

vi.mock('@etherion/stores/chat-attachments-store', () => ({
  useChatAttachmentsStore: {
    getState: () => state,
  },
}));

beforeEach(() => {
  state.addFiles.mockReset();
  state.remove.mockReset();
  state.clear.mockReset();
  state.getItems.mockReset();
  state.getItems.mockReturnValue([]);
});

describe('etherion bridge: attachments.ts', () => {
  it('addFiles throws when threadId is missing', async () => {
    await expect(addFiles('' as any, [])).rejects.toThrow(
      'threadId is required to add attachments',
    );
  });

  it('addFiles no-ops when files array is empty', async () => {
    await addFiles('t1', []);
    expect(state.addFiles).not.toHaveBeenCalled();
  });

  it('addFiles delegates to store.addFiles when threadId and files are provided', async () => {
    const file = new File(['x'], 'x.txt');

    await addFiles('t1', [file], 'b1');

    expect(state.addFiles).toHaveBeenCalledWith('t1', [file], 'b1');
  });

  it('removeAttachment throws when threadId is missing', () => {
    expect(() => removeAttachment('' as any, 'id1')).toThrow(
      'threadId is required to remove attachments',
    );
  });

  it('removeAttachment no-ops when attachmentId is empty', () => {
    removeAttachment('t1', '');
    expect(state.remove).not.toHaveBeenCalled();
  });

  it('removeAttachment delegates to store.remove', () => {
    removeAttachment('t1', 'id1', 'b1');
    expect(state.remove).toHaveBeenCalledWith('t1', 'id1', 'b1');
  });

  it('clearAttachments no-ops when threadId is empty', () => {
    clearAttachments('' as any);
    expect(state.clear).not.toHaveBeenCalled();
  });

  it('clearAttachments delegates to store.clear when threadId is non-empty', () => {
    clearAttachments('t1', 'b1');
    expect(state.clear).toHaveBeenCalledWith('t1', 'b1');
  });

  it('listAttachments returns [] when threadId is empty and does not call store', () => {
    const res = listAttachments('' as any);
    expect(res).toEqual([]);
    expect(state.getItems).not.toHaveBeenCalled();
  });

  it('listAttachments delegates to store.getItems when threadId is present', () => {
    state.getItems.mockReturnValueOnce([{ id: 'a1' }]);

    const res = listAttachments('t1', 'b1');
    expect(state.getItems).toHaveBeenCalledWith('t1', 'b1');
    expect(res).toEqual([{ id: 'a1' }]);
  });
});
