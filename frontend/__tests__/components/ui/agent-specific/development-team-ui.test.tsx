import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DevelopmentTeamUI } from '@/components/ui/agent-specific/development-team-ui'

const mockData = {
  projects: [
    { id: '1', name: 'API Refactor', status: 'in-progress', progress: 65, team: 'Backend' },
    { id: '2', name: 'UI Redesign', status: 'planning', progress: 10, team: 'Frontend' },
  ],
  sprints: [
    { id: 's1', name: 'Sprint 12', startDate: '2024-01-01', endDate: '2024-01-14', completed: 23, total: 30 },
  ],
  tasks: [
    { id: 't1', title: 'Implement authentication', status: 'done', assignee: 'John', priority: 'high' },
    { id: 't2', title: 'Fix login bug', status: 'in-progress', assignee: 'Jane', priority: 'critical' },
  ],
  codeMetrics: {
    linesOfCode: 45000,
    testCoverage: 82,
    technicalDebt: 'medium',
    codeQuality: 'A',
  },
  repositories: [
    { name: 'backend', commits: 1250, pullRequests: 45, issues: 12 },
    { name: 'frontend', commits: 890, pullRequests: 38, issues: 8 },
  ],
}

describe('DevelopmentTeamUI', () => {
  describe('Rendering', () => {
    it('should render without crashing', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByText(/development dashboard/i)).toBeInTheDocument()
    })

    it('should display projects', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByText('API Refactor')).toBeInTheDocument()
      expect(screen.getByText('UI Redesign')).toBeInTheDocument()
    })

    it('should show code metrics', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByText(/45,000/)).toBeInTheDocument() // LOC
      expect(screen.getByText(/82%/)).toBeInTheDocument() // Test coverage
    })

    it('should display loading state', () => {
      render(<DevelopmentTeamUI data={null} loading={true} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('should display error state', () => {
      const error = 'Failed to load development data'
      render(<DevelopmentTeamUI data={null} error={error} />)
      expect(screen.getByText(error)).toBeInTheDocument()
    })
  })

  describe('Sprint Management', () => {
    it('should display sprint information', () => {
      render(<DevelopmentTeamUI data={mockData} showSprints={true} />)
      expect(screen.getByText('Sprint 12')).toBeInTheDocument()
      expect(screen.getByText(/23.*30/)).toBeInTheDocument() // 23/30 completed
    })

    it('should show sprint progress', () => {
      render(<DevelopmentTeamUI data={mockData} showSprints={true} />)
      // 23/30 = 76.67%
      expect(screen.getByText(/76%/)).toBeInTheDocument()
    })

    it('should create new sprint', async () => {
      const user = userEvent.setup()
      const onSprintCreate = jest.fn()
      render(<DevelopmentTeamUI data={mockData} showSprints={true} onSprintCreate={onSprintCreate} />)

      const createBtn = screen.getByRole('button', { name: /create sprint/i })
      await user.click(createBtn)

      const nameInput = screen.getByLabelText(/sprint name/i)
      await user.type(nameInput, 'Sprint 13')

      const saveBtn = screen.getByRole('button', { name: /save/i })
      await user.click(saveBtn)

      expect(onSprintCreate).toHaveBeenCalledWith(expect.objectContaining({
        name: 'Sprint 13',
      }))
    })
  })

  describe('Task Management', () => {
    it('should display tasks', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByText('Implement authentication')).toBeInTheDocument()
      expect(screen.getByText('Fix login bug')).toBeInTheDocument()
    })

    it('should show task status', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByText('done')).toBeInTheDocument()
      expect(screen.getByText('in-progress')).toBeInTheDocument()
    })

    it('should filter tasks by status', async () => {
      const user = userEvent.setup()
      render(<DevelopmentTeamUI data={mockData} />)

      const statusFilter = screen.getByRole('combobox', { name: /status/i })
      await user.selectOptions(statusFilter, 'done')

      await waitFor(() => {
        expect(screen.getByText('Implement authentication')).toBeInTheDocument()
        expect(screen.queryByText('Fix login bug')).not.toBeInTheDocument()
      })
    })

    it('should create new task', async () => {
      const user = userEvent.setup()
      const onTaskCreate = jest.fn()
      render(<DevelopmentTeamUI data={mockData} onTaskCreate={onTaskCreate} />)

      const createBtn = screen.getByRole('button', { name: /create task/i })
      await user.click(createBtn)

      const titleInput = screen.getByLabelText(/task title/i)
      const prioritySelect = screen.getByLabelText(/priority/i)

      await user.type(titleInput, 'New Task')
      await user.selectOptions(prioritySelect, 'high')

      const saveBtn = screen.getByRole('button', { name: /save/i })
      await user.click(saveBtn)

      expect(onTaskCreate).toHaveBeenCalledWith(expect.objectContaining({
        title: 'New Task',
        priority: 'high',
      }))
    })

    it('should assign task to team member', async () => {
      const user = userEvent.setup()
      const onTaskAssign = jest.fn()
      render(<DevelopmentTeamUI data={mockData} onTaskAssign={onTaskAssign} />)

      const task = screen.getByText('Implement authentication')
      await user.click(task)

      const assignSelect = screen.getByLabelText(/assign to/i)
      await user.selectOptions(assignSelect, 'Jane')

      expect(onTaskAssign).toHaveBeenCalledWith('t1', 'Jane')
    })
  })

  describe('Code Quality Metrics', () => {
    it('should display test coverage', () => {
      render(<DevelopmentTeamUI data={mockData} showMetrics={true} />)
      expect(screen.getByText(/test coverage/i)).toBeInTheDocument()
      expect(screen.getByText('82%')).toBeInTheDocument()
    })

    it('should show technical debt indicator', () => {
      render(<DevelopmentTeamUI data={mockData} showMetrics={true} />)
      expect(screen.getByText(/technical debt/i)).toBeInTheDocument()
      expect(screen.getByText('medium')).toBeInTheDocument()
    })

    it('should display code quality grade', () => {
      render(<DevelopmentTeamUI data={mockData} showMetrics={true} />)
      expect(screen.getByText(/code quality/i)).toBeInTheDocument()
      expect(screen.getByText('A')).toBeInTheDocument()
    })

    it('should warn on low test coverage', () => {
      const lowCoverageData = {
        ...mockData,
        codeMetrics: { ...mockData.codeMetrics, testCoverage: 45 }
      }
      render(<DevelopmentTeamUI data={lowCoverageData} showMetrics={true} />)
      expect(screen.getByText(/test coverage is low/i)).toBeInTheDocument()
    })
  })

  describe('Repository Management', () => {
    it('should display repositories', () => {
      render(<DevelopmentTeamUI data={mockData} showRepositories={true} />)
      expect(screen.getByText('backend')).toBeInTheDocument()
      expect(screen.getByText('frontend')).toBeInTheDocument()
    })

    it('should show repository statistics', () => {
      render(<DevelopmentTeamUI data={mockData} showRepositories={true} />)
      expect(screen.getByText('1250')).toBeInTheDocument() // backend commits
      expect(screen.getByText('45')).toBeInTheDocument() // backend PRs
    })

    it('should filter repositories', async () => {
      const user = userEvent.setup()
      render(<DevelopmentTeamUI data={mockData} showRepositories={true} />)

      const searchInput = screen.getByPlaceholderText(/search repositories/i)
      await user.type(searchInput, 'backend')

      await waitFor(() => {
        expect(screen.getByText('backend')).toBeInTheDocument()
        expect(screen.queryByText('frontend')).not.toBeInTheDocument()
      })
    })
  })

  describe('Pull Request Management', () => {
    it('should show open pull requests', () => {
      render(<DevelopmentTeamUI data={mockData} showRepositories={true} />)
      expect(screen.getByText(/45.*pull requests/i)).toBeInTheDocument()
    })

    it('should display PR review status', () => {
      const prData = {
        ...mockData,
        pullRequests: [
          { id: 'pr1', title: 'Feature: Add login', status: 'pending', reviews: 1, required: 2 },
        ]
      }
      render(<DevelopmentTeamUI data={prData} showPullRequests={true} />)
      expect(screen.getByText(/1.*2.*reviews/i)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByRole('region', { name: /development dashboard/i })).toBeInTheDocument()
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<DevelopmentTeamUI data={mockData} />)

      await user.tab()
      const firstButton = screen.getAllByRole('button')[0]
      expect(firstButton).toHaveFocus()
    })

    it('should announce task status changes', async () => {
      const user = userEvent.setup()
      render(<DevelopmentTeamUI data={mockData} />)

      const statusFilter = screen.getByRole('combobox', { name: /status/i })
      await user.selectOptions(statusFilter, 'done')

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(/filtered/i)
      })
    })
  })

  describe('Responsive Behavior', () => {
    it('should adapt for mobile screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<DevelopmentTeamUI data={mockData} />)
      const container = screen.getByRole('region', { name: /development dashboard/i })
      expect(container).toHaveClass('mobile-layout')
    })

    it('should hide detailed metrics on small screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<DevelopmentTeamUI data={mockData} showMetrics={true} />)
      expect(screen.queryByText(/lines of code/i)).not.toBeVisible()
    })
  })

  describe('Performance', () => {
    it('should render large task lists efficiently', () => {
      const manyTasks = Array.from({ length: 500 }, (_, i) => ({
        id: `t${i}`,
        title: `Task ${i}`,
        status: 'todo',
        assignee: 'John',
        priority: 'medium',
      }))

      const startTime = performance.now()
      render(<DevelopmentTeamUI data={{ ...mockData, tasks: manyTasks }} />)
      const endTime = performance.now()

      expect(endTime - startTime).toBeLessThan(1000)
    })

    it('should debounce search input', async () => {
      const onSearch = jest.fn()
      const user = userEvent.setup()
      render(<DevelopmentTeamUI data={mockData} onSearch={onSearch} />)

      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'test query')

      await waitFor(() => {
        expect(onSearch).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Data Validation', () => {
    it('should handle missing project data', () => {
      const incompleteData = { ...mockData, projects: undefined }
      render(<DevelopmentTeamUI data={incompleteData} />)
      expect(screen.getByText(/no projects/i)).toBeInTheDocument()
    })

    it('should validate test coverage percentage', () => {
      const invalidData = {
        ...mockData,
        codeMetrics: { ...mockData.codeMetrics, testCoverage: 150 }
      }
      render(<DevelopmentTeamUI data={invalidData} showMetrics={true} />)
      expect(screen.getByText(/invalid coverage/i)).toBeInTheDocument()
    })
  })

  describe('Project Progress Tracking', () => {
    it('should display project progress bars', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      const progressBars = screen.getAllByRole('progressbar')
      expect(progressBars.length).toBeGreaterThan(0)
    })

    it('should show project status badges', () => {
      render(<DevelopmentTeamUI data={mockData} />)
      expect(screen.getByText('in-progress')).toBeInTheDocument()
      expect(screen.getByText('planning')).toBeInTheDocument()
    })

    it('should sort projects by progress', async () => {
      const user = userEvent.setup()
      render(<DevelopmentTeamUI data={mockData} />)

      const sortButton = screen.getByRole('button', { name: /sort/i })
      await user.click(sortButton)

      const progressOption = screen.getByText(/progress/i)
      await user.click(progressOption)

      await waitFor(() => {
        const projects = screen.getAllByRole('listitem')
        expect(projects[0]).toHaveTextContent('API Refactor')
      })
    })
  })
})
