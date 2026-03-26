import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ContentTeamUI } from '@/components/ui/agent-specific/content-team-ui'

// Mock data
const mockContentData = {
  drafts: [
    { id: '1', title: 'Blog Post Draft', content: 'Lorem ipsum...', status: 'draft', wordCount: 500 },
    { id: '2', title: 'Social Media Post', content: 'Short content', status: 'review', wordCount: 50 },
  ],
  templates: [
    { id: 't1', name: 'Blog Template', category: 'blog', usage: 45 },
    { id: 't2', name: 'Email Template', category: 'email', usage: 30 },
  ],
  seoMetrics: {
    readabilityScore: 75,
    keywordDensity: 2.5,
    metaDescriptionLength: 155,
    headingStructure: 'good',
  },
  contentCalendar: [
    { date: '2024-01-15', title: 'Product Launch', status: 'scheduled' },
    { date: '2024-01-20', title: 'Newsletter', status: 'draft' },
  ],
}

const mockEditorContent = {
  text: 'This is sample content',
  html: '<p>This is sample content</p>',
  markdown: '**This is sample content**',
}

describe('ContentTeamUI', () => {
  describe('Rendering', () => {
    it('should render without crashing', () => {
      render(<ContentTeamUI data={mockContentData} />)
      expect(screen.getByText(/content dashboard/i)).toBeInTheDocument()
    })

    it('should display all content drafts', () => {
      render(<ContentTeamUI data={mockContentData} />)

      expect(screen.getByText('Blog Post Draft')).toBeInTheDocument()
      expect(screen.getByText('Social Media Post')).toBeInTheDocument()
    })

    it('should show content templates', () => {
      render(<ContentTeamUI data={mockContentData} showTemplates={true} />)

      expect(screen.getByText('Blog Template')).toBeInTheDocument()
      expect(screen.getByText('Email Template')).toBeInTheDocument()
    })

    it('should display SEO metrics when available', () => {
      render(<ContentTeamUI data={mockContentData} showSEOMetrics={true} />)

      expect(screen.getByText(/readability score/i)).toBeInTheDocument()
      expect(screen.getByText('75')).toBeInTheDocument()
      expect(screen.getByText(/keyword density/i)).toBeInTheDocument()
    })

    it('should render loading state', () => {
      render(<ContentTeamUI data={null} loading={true} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('should display error message', () => {
      const error = 'Failed to load content'
      render(<ContentTeamUI data={null} error={error} />)
      expect(screen.getByText(error)).toBeInTheDocument()
    })
  })

  describe('Rich Text Editor', () => {
    it('should render rich text editor when enabled', () => {
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)
      expect(screen.getByRole('textbox', { name: /content editor/i })).toBeInTheDocument()
    })

    it('should allow text input in editor', async () => {
      const user = userEvent.setup()
      const onContentChange = jest.fn()
      render(<ContentTeamUI data={mockContentData} showEditor={true} onContentChange={onContentChange} />)

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'New content')

      await waitFor(() => {
        expect(onContentChange).toHaveBeenCalled()
      })
    })

    it('should support formatting toolbar actions', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const boldButton = screen.getByRole('button', { name: /bold/i })
      const italicButton = screen.getByRole('button', { name: /italic/i })
      const underlineButton = screen.getByRole('button', { name: /underline/i })

      expect(boldButton).toBeInTheDocument()
      expect(italicButton).toBeInTheDocument()
      expect(underlineButton).toBeInTheDocument()

      await user.click(boldButton)
      expect(boldButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('should support heading levels', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const headingDropdown = screen.getByRole('button', { name: /heading/i })
      await user.click(headingDropdown)

      expect(screen.getByText('Heading 1')).toBeInTheDocument()
      expect(screen.getByText('Heading 2')).toBeInTheDocument()
      expect(screen.getByText('Heading 3')).toBeInTheDocument()
    })

    it('should insert links', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const linkButton = screen.getByRole('button', { name: /insert link/i })
      await user.click(linkButton)

      const urlInput = screen.getByPlaceholderText(/enter url/i)
      await user.type(urlInput, 'https://example.com')

      const insertButton = screen.getByRole('button', { name: /insert/i })
      await user.click(insertButton)

      await waitFor(() => {
        expect(screen.queryByPlaceholderText(/enter url/i)).not.toBeInTheDocument()
      })
    })

    it('should insert images', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const imageButton = screen.getByRole('button', { name: /insert image/i })
      await user.click(imageButton)

      const imageInput = screen.getByLabelText(/image url/i)
      await user.type(imageInput, 'https://example.com/image.jpg')

      const insertButton = screen.getByRole('button', { name: /insert/i })
      await user.click(insertButton)

      await waitFor(() => {
        expect(screen.getByRole('img')).toHaveAttribute('src', 'https://example.com/image.jpg')
      })
    })

    it('should support undo/redo', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const undoButton = screen.getByRole('button', { name: /undo/i })
      const redoButton = screen.getByRole('button', { name: /redo/i })

      expect(undoButton).toBeDisabled()
      expect(redoButton).toBeDisabled()

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'Text')

      expect(undoButton).toBeEnabled()
    })

    it('should show word count', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'One two three four five')

      await waitFor(() => {
        expect(screen.getByText(/5 words/i)).toBeInTheDocument()
      })
    })

    it('should support character count', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'Hello')

      await waitFor(() => {
        expect(screen.getByText(/5 characters/i)).toBeInTheDocument()
      })
    })
  })

  describe('Content Templates', () => {
    it('should display template library', () => {
      render(<ContentTeamUI data={mockContentData} showTemplates={true} />)
      expect(screen.getByText(/template library/i)).toBeInTheDocument()
    })

    it('should filter templates by category', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showTemplates={true} />)

      const categoryFilter = screen.getByRole('combobox', { name: /category/i })
      await user.selectOptions(categoryFilter, 'blog')

      await waitFor(() => {
        expect(screen.getByText('Blog Template')).toBeInTheDocument()
        expect(screen.queryByText('Email Template')).not.toBeInTheDocument()
      })
    })

    it('should load template into editor', async () => {
      const user = userEvent.setup()
      const onTemplateLoad = jest.fn()
      render(
        <ContentTeamUI
          data={mockContentData}
          showTemplates={true}
          showEditor={true}
          onTemplateLoad={onTemplateLoad}
        />
      )

      const templateCard = screen.getByText('Blog Template').closest('div')
      const useButton = templateCard?.querySelector('button')

      if (useButton) {
        await user.click(useButton)
        expect(onTemplateLoad).toHaveBeenCalledWith(expect.objectContaining({ id: 't1' }))
      }
    })

    it('should create new template', async () => {
      const user = userEvent.setup()
      const onTemplateCreate = jest.fn()
      render(<ContentTeamUI data={mockContentData} showTemplates={true} onTemplateCreate={onTemplateCreate} />)

      const createButton = screen.getByRole('button', { name: /create template/i })
      await user.click(createButton)

      const nameInput = screen.getByLabelText(/template name/i)
      await user.type(nameInput, 'New Template')

      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      expect(onTemplateCreate).toHaveBeenCalledWith(expect.objectContaining({
        name: 'New Template'
      }))
    })

    it('should show template usage statistics', () => {
      render(<ContentTeamUI data={mockContentData} showTemplates={true} />)
      expect(screen.getByText(/45/)).toBeInTheDocument() // Blog template usage
      expect(screen.getByText(/30/)).toBeInTheDocument() // Email template usage
    })
  })

  describe('SEO Optimization', () => {
    it('should display SEO metrics panel', () => {
      render(<ContentTeamUI data={mockContentData} showSEOMetrics={true} />)
      expect(screen.getByText(/seo metrics/i)).toBeInTheDocument()
    })

    it('should show readability score with color indicator', () => {
      render(<ContentTeamUI data={mockContentData} showSEOMetrics={true} />)
      const scoreElement = screen.getByText('75')
      expect(scoreElement).toHaveClass('score-good')
    })

    it('should display keyword density warnings', () => {
      const highDensityData = {
        ...mockContentData,
        seoMetrics: { ...mockContentData.seoMetrics, keywordDensity: 5.0 }
      }
      render(<ContentTeamUI data={highDensityData} showSEOMetrics={true} />)
      expect(screen.getByText(/keyword density too high/i)).toBeInTheDocument()
    })

    it('should validate meta description length', () => {
      const invalidMetaData = {
        ...mockContentData,
        seoMetrics: { ...mockContentData.seoMetrics, metaDescriptionLength: 200 }
      }
      render(<ContentTeamUI data={invalidMetaData} showSEOMetrics={true} />)
      expect(screen.getByText(/meta description too long/i)).toBeInTheDocument()
    })

    it('should provide SEO improvement suggestions', () => {
      render(<ContentTeamUI data={mockContentData} showSEOMetrics={true} />)
      expect(screen.getByText(/suggestions/i)).toBeInTheDocument()
    })
  })

  describe('Content Calendar', () => {
    it('should display content calendar view', () => {
      render(<ContentTeamUI data={mockContentData} showCalendar={true} />)
      expect(screen.getByText(/content calendar/i)).toBeInTheDocument()
    })

    it('should show scheduled content items', () => {
      render(<ContentTeamUI data={mockContentData} showCalendar={true} />)
      expect(screen.getByText('Product Launch')).toBeInTheDocument()
      expect(screen.getByText('Newsletter')).toBeInTheDocument()
    })

    it('should filter by status', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showCalendar={true} />)

      const statusFilter = screen.getByRole('combobox', { name: /status/i })
      await user.selectOptions(statusFilter, 'scheduled')

      await waitFor(() => {
        expect(screen.getByText('Product Launch')).toBeInTheDocument()
        expect(screen.queryByText('Newsletter')).not.toBeInTheDocument()
      })
    })

    it('should allow scheduling new content', async () => {
      const user = userEvent.setup()
      const onSchedule = jest.fn()
      render(<ContentTeamUI data={mockContentData} showCalendar={true} onSchedule={onSchedule} />)

      const scheduleButton = screen.getByRole('button', { name: /schedule content/i })
      await user.click(scheduleButton)

      const titleInput = screen.getByLabelText(/title/i)
      const dateInput = screen.getByLabelText(/date/i)

      await user.type(titleInput, 'New Post')
      await user.type(dateInput, '2024-02-01')

      const confirmButton = screen.getByRole('button', { name: /confirm/i })
      await user.click(confirmButton)

      expect(onSchedule).toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)
      expect(screen.getByRole('region', { name: /content dashboard/i })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /content editor/i })).toHaveAttribute('aria-label')
    })

    it('should support keyboard navigation in editor toolbar', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const boldButton = screen.getByRole('button', { name: /bold/i })
      boldButton.focus()
      expect(boldButton).toHaveFocus()

      await user.keyboard('{Tab}')
      const italicButton = screen.getByRole('button', { name: /italic/i })
      expect(italicButton).toHaveFocus()
    })

    it('should announce editor changes to screen readers', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} />)

      const boldButton = screen.getByRole('button', { name: /bold/i })
      await user.click(boldButton)

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(/bold formatting applied/i)
      })
    })

    it('should have proper heading hierarchy', () => {
      render(<ContentTeamUI data={mockContentData} showEditor={true} showTemplates={true} />)
      const headings = screen.getAllByRole('heading')
      expect(headings[0].tagName).toBe('H2')
    })
  })

  describe('Responsive Behavior', () => {
    it('should adapt for mobile screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<ContentTeamUI data={mockContentData} showEditor={true} />)
      const container = screen.getByRole('region', { name: /content dashboard/i })
      expect(container).toHaveClass('mobile-layout')
    })

    it('should show simplified toolbar on mobile', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<ContentTeamUI data={mockContentData} showEditor={true} />)
      expect(screen.queryByRole('button', { name: /advanced options/i })).not.toBeVisible()
    })
  })

  describe('Auto-save Functionality', () => {
    it('should auto-save content after delay', async () => {
      jest.useFakeTimers()
      const onAutoSave = jest.fn()
      const user = userEvent.setup({ delay: null })

      render(<ContentTeamUI data={mockContentData} showEditor={true} onAutoSave={onAutoSave} />)

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'Auto save test')

      jest.advanceTimersByTime(3000)

      await waitFor(() => {
        expect(onAutoSave).toHaveBeenCalled()
      })

      jest.useRealTimers()
    })

    it('should show auto-save indicator', async () => {
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} enableAutoSave={true} />)

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'Test')

      await waitFor(() => {
        expect(screen.getByText(/saving/i)).toBeInTheDocument()
      }, { timeout: 4000 })
    })
  })

  describe('Performance', () => {
    it('should render large content efficiently', () => {
      const largeContent = Array.from({ length: 100 }, (_, i) => ({
        id: `${i}`,
        title: `Draft ${i}`,
        content: 'Lorem ipsum '.repeat(100),
        status: 'draft',
        wordCount: 1000
      }))

      const startTime = performance.now()
      render(<ContentTeamUI data={{ ...mockContentData, drafts: largeContent }} />)
      const endTime = performance.now()

      expect(endTime - startTime).toBeLessThan(1000)
    })

    it('should debounce editor input', async () => {
      const onChange = jest.fn()
      const user = userEvent.setup()
      render(<ContentTeamUI data={mockContentData} showEditor={true} onContentChange={onChange} />)

      const editor = screen.getByRole('textbox', { name: /content editor/i })
      await user.type(editor, 'Quick typing')

      // Should debounce and call less than character count
      await waitFor(() => {
        expect(onChange).toHaveBeenCalledTimes(1)
      })
    })
  })
})
