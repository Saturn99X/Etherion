import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getKnowledgeItemDetails,
  ingestToKnowledgeBase,
  listKnowledgeItems,
  type KnowledgeItem,
} from '../knowledge';
import * as repository from '../repository';

vi.mock('../repository', () => ({
  listAssets: vi.fn(),
  getAsset: vi.fn(),
}));

const repoMock = vi.mocked(repository);

beforeEach(() => {
  repoMock.listAssets.mockReset();
  repoMock.getAsset.mockReset();
});

describe('etherion bridge: knowledge.ts', () => {
  it('ingestToKnowledgeBase rejects with explicit not-implemented error', async () => {
    await expect(ingestToKnowledgeBase({ kind: 'url', url: 'https://example.com' })).rejects.toThrow(
      'KnowledgeBaseBridge: ingestToKnowledgeBase is not implemented on the frontend; ingestion is triggered via backend jobs or connectors.',
    );
  });

  it('listKnowledgeItems(number) normalizes to options and forwards to listAssets', async () => {
    const items: KnowledgeItem[] = [
      {
        assetId: 'a1',
        jobId: null,
        filename: 'doc.txt',
        mimeType: 'text/plain',
        sizeBytes: 10,
        gcsUri: 'gs://bkt/doc.txt',
        createdAt: '2024-01-01T00:00:00Z',
        downloadUrl: null,
        previewBase64: null,
      },
    ];

    repoMock.listAssets.mockResolvedValueOnce(items as any);

    const result = await listKnowledgeItems(25);

    expect(repoMock.listAssets).toHaveBeenCalledWith({
      limit: 25,
      jobId: null,
      includeDownload: false,
    });
    expect(result).toEqual(items);
  });

  it('listKnowledgeItems(options) passes through options with defaults', async () => {
    const items: KnowledgeItem[] = [];
    repoMock.listAssets.mockResolvedValueOnce(items as any);

    const result = await listKnowledgeItems({ limit: 5, jobId: 'job-1', includeDownload: true });

    expect(repoMock.listAssets).toHaveBeenCalledWith({
      limit: 5,
      jobId: 'job-1',
      includeDownload: true,
    });
    expect(result).toEqual(items);
  });

  it('getKnowledgeItemDetails validates id and does not call getAsset when empty', async () => {
    await expect(getKnowledgeItemDetails('')).rejects.toThrow(
      'id is required to load knowledge item details',
    );
    expect(repoMock.getAsset).not.toHaveBeenCalled();
  });

  it('getKnowledgeItemDetails trims id and forwards to getAsset', async () => {
    const item: KnowledgeItem = {
      assetId: 'a2',
      jobId: null,
      filename: 'note.md',
      mimeType: 'text/markdown',
      sizeBytes: 20,
      gcsUri: 'gs://bkt/note.md',
      createdAt: '2024-01-02T00:00:00Z',
      downloadUrl: null,
      previewBase64: null,
    };

    repoMock.getAsset.mockResolvedValueOnce(item as any);

    const result = await getKnowledgeItemDetails('  a2  ');
    expect(repoMock.getAsset).toHaveBeenCalledWith('a2');
    expect(result).toEqual(item);
  });
});
