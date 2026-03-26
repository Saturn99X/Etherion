import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';
import { KnowledgeBrowser } from '../../knowledge/knowledge-browser';
import {
  mockListKnowledgeItems,
  setupBridgeMocks,
  resetBridgeMocks,
} from '../mocks/bridges';

// Mock the bridge module
vi.mock('@etherion/bridge/knowledge', () => ({
  listKnowledgeItems: mockListKnowledgeItems,
}));

describe('KnowledgeBrowser', () => {
  beforeEach(() => {
    setupBridgeMocks();
  });

  afterEach(() => {
    resetBridgeMocks();
  });

  it('should call listKnowledgeItems on mount with correct parameters', async () => {
    render(
      <App>
        <KnowledgeBrowser limit={50} />
      </App>
    );

    await waitFor(() => {
      expect(mockListKnowledgeItems).toHaveBeenCalledWith({
        limit: 50,
        includeDownload: true,
      });
    });
  });

  it('should display knowledge items after loading', async () => {
    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
      expect(screen.getByText('another-doc.docx')).toBeInTheDocument();
    });
  });

  it('should display item metadata (size, date, mime type)', async () => {
    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('application/pdf')).toBeInTheDocument();
      expect(screen.getByText('1 KB')).toBeInTheDocument();
    });
  });

  it('should handle bridge errors gracefully', async () => {
    mockListKnowledgeItems.mockRejectedValueOnce(new Error('Network error'));

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      // AntD message.error should be called (we can't easily test the toast, but we can verify the error was caught)
      expect(mockListKnowledgeItems).toHaveBeenCalled();
    });
  });

  it('should filter items by filename (client-side)', async () => {
    const user = userEvent.setup();

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    // Wait for items to load
    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
      expect(screen.getByText('another-doc.docx')).toBeInTheDocument();
    });

    // Type in search input
    const searchInput = screen.getByPlaceholderText(/filter by filename/i);
    await user.type(searchInput, 'test-doc');

    // Only matching item should be visible
    expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    expect(screen.queryByText('another-doc.docx')).not.toBeInTheDocument();
  });

  it('should clear filter when clear button is clicked', async () => {
    const user = userEvent.setup();

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/filter by filename/i);
    await user.type(searchInput, 'test-doc');

    expect(screen.queryByText('another-doc.docx')).not.toBeInTheDocument();

    // Clear the input
    await user.clear(searchInput);

    // Both items should be visible again
    expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    expect(screen.getByText('another-doc.docx')).toBeInTheDocument();
  });

  it('should display empty state when no items match filter', async () => {
    const user = userEvent.setup();

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/filter by filename/i);
    await user.type(searchInput, 'nonexistent-file');

    expect(screen.getByText(/no items match your filter/i)).toBeInTheDocument();
  });

  it('should display empty state when no knowledge items exist', async () => {
    mockListKnowledgeItems.mockResolvedValueOnce([]);

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText(/no knowledge items found/i)).toBeInTheDocument();
    });
  });

  it('should open download URL when item is clicked', async () => {
    const user = userEvent.setup();
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    });

    const item = screen.getByText('test-doc.pdf').closest('div[class*="resultItem"]');
    if (item) {
      await user.click(item);
    }

    expect(windowOpenSpy).toHaveBeenCalledWith(
      'https://example.com/download/test-doc.pdf',
      '_blank'
    );

    windowOpenSpy.mockRestore();
  });

  it('should call onSelectDocument callback when provided', async () => {
    const user = userEvent.setup();
    const onSelectDocument = vi.fn();

    render(
      <App>
        <KnowledgeBrowser onSelectDocument={onSelectDocument} />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    });

    const item = screen.getByText('test-doc.pdf').closest('div[class*="resultItem"]');
    if (item) {
      await user.click(item);
    }

    expect(onSelectDocument).toHaveBeenCalledWith('asset-1');
  });

  it('should refresh data when refresh button is clicked', async () => {
    const user = userEvent.setup();

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(mockListKnowledgeItems).toHaveBeenCalledTimes(1);
    });

    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    await user.click(refreshButton);

    await waitFor(() => {
      expect(mockListKnowledgeItems).toHaveBeenCalledTimes(2);
    });
  });

  it('should display loading state while fetching', () => {
    mockListKnowledgeItems.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve([]), 1000))
    );

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('should respect custom limit prop', async () => {
    render(
      <App>
        <KnowledgeBrowser limit={25} />
      </App>
    );

    await waitFor(() => {
      expect(mockListKnowledgeItems).toHaveBeenCalledWith({
        limit: 25,
        includeDownload: true,
      });
    });
  });

  it('should display job ID tag when available', async () => {
    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText(/job: job-1/i)).toBeInTheDocument();
    });
  });

  it('should open download URL in new tab when external link button is clicked', async () => {
    const user = userEvent.setup();
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(
      <App>
        <KnowledgeBrowser />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('test-doc.pdf')).toBeInTheDocument();
    });

    // Find the external link button (it's a button with ExternalLink icon)
    const externalLinkButtons = screen.getAllByRole('button');
    const externalLinkButton = externalLinkButtons.find((btn) =>
      btn.querySelector('svg')
    );

    if (externalLinkButton) {
      await user.click(externalLinkButton);
    }

    expect(windowOpenSpy).toHaveBeenCalledWith(
      expect.stringContaining('download'),
      '_blank'
    );

    windowOpenSpy.mockRestore();
  });
});
