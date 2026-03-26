import { vi } from 'vitest';
import type { KnowledgeItem } from '@etherion/bridge/knowledge';

// Knowledge Bridge Mock
export const mockListKnowledgeItems = vi.fn<any, Promise<KnowledgeItem[]>>();

// Chat Bridge Mock
export const mockSendGoalAndStream = vi.fn();

// Session Bridge Mock
export const mockGetThreads = vi.fn();

// Repository Bridge Mock
export const mockListAssets = vi.fn();

// Setup default mock implementations
export const setupBridgeMocks = () => {
  mockListKnowledgeItems.mockResolvedValue([
    {
      assetId: 'asset-1',
      filename: 'test-doc.pdf',
      mimeType: 'application/pdf',
      sizeBytes: 1024,
      createdAt: '2026-01-21T00:00:00Z',
      downloadUrl: 'https://example.com/download/test-doc.pdf',
      jobId: 'job-1',
    },
    {
      assetId: 'asset-2',
      filename: 'another-doc.docx',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      sizeBytes: 2048,
      createdAt: '2026-01-20T00:00:00Z',
      downloadUrl: 'https://example.com/download/another-doc.docx',
      jobId: 'job-2',
    },
  ]);

  mockGetThreads.mockResolvedValue([
    {
      id: 'thread-1',
      title: 'Test Thread 1',
      createdAt: '2026-01-21T00:00:00Z',
      updatedAt: '2026-01-21T00:00:00Z',
    },
    {
      id: 'thread-2',
      title: 'Test Thread 2',
      createdAt: '2026-01-20T00:00:00Z',
      updatedAt: '2026-01-20T00:00:00Z',
    },
  ]);

  mockListAssets.mockResolvedValue([
    {
      id: 'asset-1',
      filename: 'output.txt',
      mimeType: 'text/plain',
      sizeBytes: 512,
      createdAt: '2026-01-21T00:00:00Z',
      downloadUrl: 'https://example.com/download/output.txt',
    },
    {
      id: 'asset-2',
      filename: 'result.json',
      mimeType: 'application/json',
      sizeBytes: 1024,
      createdAt: '2026-01-20T00:00:00Z',
      downloadUrl: 'https://example.com/download/result.json',
    },
  ]);

  mockSendGoalAndStream.mockResolvedValue({
    jobId: 'job-new',
    threadId: 'thread-new',
  });
};

// Reset all bridge mocks
export const resetBridgeMocks = () => {
  mockListKnowledgeItems.mockReset();
  mockSendGoalAndStream.mockReset();
  mockGetThreads.mockReset();
  mockListAssets.mockReset();
};

// Mock the bridge modules
export const mockBridgeModules = () => {
  vi.mock('@etherion/bridge/knowledge', () => ({
    listKnowledgeItems: mockListKnowledgeItems,
  }));

  vi.mock('@etherion/bridge/chat', () => ({
    sendGoalAndStream: mockSendGoalAndStream,
  }));

  vi.mock('@etherion/bridge/session', () => ({
    getThreads: mockGetThreads,
  }));

  vi.mock('@etherion/bridge/repository', () => ({
    listAssets: mockListAssets,
  }));
};
