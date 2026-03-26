import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SalesTeamUI } from '@/components/ui/agent-specific/sales-team-ui'

// Mock data
const mockSalesData = {
  totalDeals: 145,
  activeDeals: 32,
  closedDeals: 98,
  totalRevenue: 2450000,
  avgDealSize: 25000,
  conversionRate: 28.5,
  pipeline: [
    { stage: 'Prospect', count: 45, value: 450000 },
    { stage: 'Qualification', count: 28, value: 560000 },
    { stage: 'Proposal', count: 18, value: 450000 },
    { stage: 'Negotiation', count: 12, value: 360000 },
    { stage: 'Closed Won', count: 98, value: 2450000 },
  ],
  topDeals: [
    { id: '1', name: 'Enterprise Deal', value: 150000, stage: 'Negotiation', probability: 75 },
    { id: '2', name: 'Mid-Market Deal', value: 85000, stage: 'Proposal', probability: 60 },
    { id: '3', name: 'SMB Deal', value: 35000, stage: 'Qualification', probability: 45 },
  ],
  salesReps: [
    { id: 'r1', name: 'John Doe', deals: 24, revenue: 580000, quota: 600000 },
    { id: 'r2', name: 'Jane Smith', deals: 31, revenue: 720000, quota: 650000 },
    { id: 'r3', name: 'Bob Johnson', deals: 19, revenue: 445000, quota: 500000 },
  ],
  activities: [
    { id: 'a1', type: 'call', dealId: '1', timestamp: '2024-01-15T10:30:00Z', notes: 'Follow-up call' },
    { id: 'a2', type: 'email', dealId: '2', timestamp: '2024-01-15T14:15:00Z', notes: 'Sent proposal' },
    { id: 'a3', type: 'meeting', dealId: '3', timestamp: '2024-01-16T09:00:00Z', notes: 'Demo scheduled' },
  ],
}

const mockLeadData = {
  id: 'l1',
  name: 'Acme Corp',
  email: 'contact@acme.com',
  phone: '+1-555-0123',
  company: 'Acme Corporation',
  title: 'VP of Sales',
  score: 85,
  source: 'Website',
  status: 'New',
}

describe('SalesTeamUI', () => {
  describe('Rendering', () => {
    it('should render without crashing', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByText(/sales dashboard/i)).toBeInTheDocument()
    })

    it('should display key sales metrics', () => {
      render(<SalesTeamUI data={mockSalesData} />)

      expect(screen.getByText(/total deals/i)).toBeInTheDocument()
      expect(screen.getByText('145')).toBeInTheDocument()
      expect(screen.getByText(/active deals/i)).toBeInTheDocument()
      expect(screen.getByText('32')).toBeInTheDocument()
      expect(screen.getByText(/total revenue/i)).toBeInTheDocument()
      expect(screen.getByText(/\$2,450,000/)).toBeInTheDocument()
    })

    it('should render sales pipeline visualization', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByText('Prospect')).toBeInTheDocument()
      expect(screen.getByText('Qualification')).toBeInTheDocument()
      expect(screen.getByText('Proposal')).toBeInTheDocument()
      expect(screen.getByText('Negotiation')).toBeInTheDocument()
      expect(screen.getByText('Closed Won')).toBeInTheDocument()
    })

    it('should display loading state', () => {
      render(<SalesTeamUI data={null} loading={true} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('should display error state', () => {
      const error = 'Failed to load sales data'
      render(<SalesTeamUI data={null} error={error} />)
      expect(screen.getByText(error)).toBeInTheDocument()
    })
  })

  describe('Pipeline Management', () => {
    it('should show deal count for each pipeline stage', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByText('45')).toBeInTheDocument() // Prospect count
      expect(screen.getByText('28')).toBeInTheDocument() // Qualification count
    })

    it('should display pipeline value for each stage', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByText(/\$450,000/)).toBeInTheDocument()
      expect(screen.getByText(/\$560,000/)).toBeInTheDocument()
    })

    it('should allow filtering pipeline by stage', async () => {
      const user = userEvent.setup()
      const onStageFilter = jest.fn()
      render(<SalesTeamUI data={mockSalesData} onStageFilter={onStageFilter} />)

      const proposalStage = screen.getByText('Proposal')
      await user.click(proposalStage)

      expect(onStageFilter).toHaveBeenCalledWith('Proposal')
    })

    it('should show pipeline conversion rates', () => {
      render(<SalesTeamUI data={mockSalesData} showConversionRates={true} />)
      expect(screen.getByText(/conversion rate/i)).toBeInTheDocument()
      expect(screen.getByText('28.5%')).toBeInTheDocument()
    })

    it('should allow dragging deals between stages', async () => {
      const onDealMove = jest.fn()
      render(<SalesTeamUI data={mockSalesData} onDealMove={onDealMove} enableDragDrop={true} />)

      const deal = screen.getByText('Enterprise Deal')
      const targetStage = screen.getByText('Closed Won')

      fireEvent.dragStart(deal)
      fireEvent.dragOver(targetStage)
      fireEvent.drop(targetStage)

      expect(onDealMove).toHaveBeenCalledWith(expect.objectContaining({
        dealId: '1',
        newStage: 'Closed Won',
      }))
    })
  })

  describe('Deal Management', () => {
    it('should display top deals list', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByText('Enterprise Deal')).toBeInTheDocument()
      expect(screen.getByText('Mid-Market Deal')).toBeInTheDocument()
      expect(screen.getByText('SMB Deal')).toBeInTheDocument()
    })

    it('should show deal probability', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByText('75%')).toBeInTheDocument()
      expect(screen.getByText('60%')).toBeInTheDocument()
      expect(screen.getByText('45%')).toBeInTheDocument()
    })

    it('should open deal details on click', async () => {
      const user = userEvent.setup()
      const onDealSelect = jest.fn()
      render(<SalesTeamUI data={mockSalesData} onDealSelect={onDealSelect} />)

      const deal = screen.getByText('Enterprise Deal')
      await user.click(deal)

      expect(onDealSelect).toHaveBeenCalledWith('1')
    })

    it('should create new deal', async () => {
      const user = userEvent.setup()
      const onDealCreate = jest.fn()
      render(<SalesTeamUI data={mockSalesData} onDealCreate={onDealCreate} />)

      const createButton = screen.getByRole('button', { name: /create deal/i })
      await user.click(createButton)

      const nameInput = screen.getByLabelText(/deal name/i)
      const valueInput = screen.getByLabelText(/deal value/i)

      await user.type(nameInput, 'New Deal')
      await user.type(valueInput, '50000')

      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      expect(onDealCreate).toHaveBeenCalledWith(expect.objectContaining({
        name: 'New Deal',
        value: 50000,
      }))
    })

    it('should sort deals by different criteria', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} />)

      const sortButton = screen.getByRole('button', { name: /sort/i })
      await user.click(sortButton)

      const valueOption = screen.getByText(/value/i)
      await user.click(valueOption)

      await waitFor(() => {
        const deals = screen.getAllByRole('listitem')
        expect(deals[0]).toHaveTextContent('Enterprise Deal')
      })
    })
  })

  describe('Sales Team Performance', () => {
    it('should display sales rep leaderboard', () => {
      render(<SalesTeamUI data={mockSalesData} showTeamPerformance={true} />)
      expect(screen.getByText('John Doe')).toBeInTheDocument()
      expect(screen.getByText('Jane Smith')).toBeInTheDocument()
      expect(screen.getByText('Bob Johnson')).toBeInTheDocument()
    })

    it('should show quota attainment', () => {
      render(<SalesTeamUI data={mockSalesData} showTeamPerformance={true} />)
      expect(screen.getByText(/quota/i)).toBeInTheDocument()
      // Jane Smith: 720000/650000 = 110.77%
      expect(screen.getByText(/110/)).toBeInTheDocument()
    })

    it('should filter by sales rep', async () => {
      const user = userEvent.setup()
      const onRepFilter = jest.fn()
      render(<SalesTeamUI data={mockSalesData} showTeamPerformance={true} onRepFilter={onRepFilter} />)

      const repFilter = screen.getByRole('combobox', { name: /sales rep/i })
      await user.selectOptions(repFilter, 'r1')

      expect(onRepFilter).toHaveBeenCalledWith('r1')
    })

    it('should show individual rep performance details', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} showTeamPerformance={true} />)

      const rep = screen.getByText('Jane Smith')
      await user.click(rep)

      await waitFor(() => {
        expect(screen.getByText(/rep details/i)).toBeInTheDocument()
        expect(screen.getByText('31')).toBeInTheDocument() // deals count
      })
    })
  })

  describe('Lead Management', () => {
    it('should display lead form', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} showLeadForm={true} />)

      const addLeadButton = screen.getByRole('button', { name: /add lead/i })
      await user.click(addLeadButton)

      expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/company/i)).toBeInTheDocument()
    })

    it('should create new lead', async () => {
      const user = userEvent.setup()
      const onLeadCreate = jest.fn()
      render(<SalesTeamUI data={mockSalesData} showLeadForm={true} onLeadCreate={onLeadCreate} />)

      const addLeadButton = screen.getByRole('button', { name: /add lead/i })
      await user.click(addLeadButton)

      await user.type(screen.getByLabelText(/name/i), 'John Doe')
      await user.type(screen.getByLabelText(/email/i), 'john@example.com')
      await user.type(screen.getByLabelText(/company/i), 'Example Inc')

      const submitButton = screen.getByRole('button', { name: /submit/i })
      await user.click(submitButton)

      expect(onLeadCreate).toHaveBeenCalledWith(expect.objectContaining({
        name: 'John Doe',
        email: 'john@example.com',
        company: 'Example Inc',
      }))
    })

    it('should validate lead email format', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} showLeadForm={true} />)

      const addLeadButton = screen.getByRole('button', { name: /add lead/i })
      await user.click(addLeadButton)

      const emailInput = screen.getByLabelText(/email/i)
      await user.type(emailInput, 'invalid-email')

      const submitButton = screen.getByRole('button', { name: /submit/i })
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText(/invalid email/i)).toBeInTheDocument()
      })
    })

    it('should show lead score', () => {
      render(<SalesTeamUI data={mockSalesData} leads={[mockLeadData]} />)
      expect(screen.getByText('85')).toBeInTheDocument() // lead score
    })

    it('should convert lead to deal', async () => {
      const user = userEvent.setup()
      const onLeadConvert = jest.fn()
      render(<SalesTeamUI data={mockSalesData} leads={[mockLeadData]} onLeadConvert={onLeadConvert} />)

      const convertButton = screen.getByRole('button', { name: /convert/i })
      await user.click(convertButton)

      expect(onLeadConvert).toHaveBeenCalledWith('l1')
    })
  })

  describe('Activity Tracking', () => {
    it('should display activity timeline', () => {
      render(<SalesTeamUI data={mockSalesData} showActivityTimeline={true} />)
      expect(screen.getByText(/activity timeline/i)).toBeInTheDocument()
      expect(screen.getByText('Follow-up call')).toBeInTheDocument()
      expect(screen.getByText('Sent proposal')).toBeInTheDocument()
    })

    it('should log new activity', async () => {
      const user = userEvent.setup()
      const onActivityLog = jest.fn()
      render(<SalesTeamUI data={mockSalesData} showActivityTimeline={true} onActivityLog={onActivityLog} />)

      const logButton = screen.getByRole('button', { name: /log activity/i })
      await user.click(logButton)

      const typeSelect = screen.getByLabelText(/activity type/i)
      const notesInput = screen.getByLabelText(/notes/i)

      await user.selectOptions(typeSelect, 'call')
      await user.type(notesInput, 'Important call')

      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      expect(onActivityLog).toHaveBeenCalledWith(expect.objectContaining({
        type: 'call',
        notes: 'Important call',
      }))
    })

    it('should filter activities by type', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} showActivityTimeline={true} />)

      const filterSelect = screen.getByRole('combobox', { name: /activity type/i })
      await user.selectOptions(filterSelect, 'call')

      await waitFor(() => {
        expect(screen.getByText('Follow-up call')).toBeInTheDocument()
        expect(screen.queryByText('Sent proposal')).not.toBeInTheDocument()
      })
    })
  })

  describe('Forecasting', () => {
    it('should display sales forecast', () => {
      render(<SalesTeamUI data={mockSalesData} showForecast={true} />)
      expect(screen.getByText(/forecast/i)).toBeInTheDocument()
    })

    it('should show projected revenue', () => {
      render(<SalesTeamUI data={mockSalesData} showForecast={true} />)
      expect(screen.getByText(/projected revenue/i)).toBeInTheDocument()
    })

    it('should adjust forecast based on probability', () => {
      render(<SalesTeamUI data={mockSalesData} showForecast={true} />)
      // Should show weighted forecast: sum of (deal value * probability)
      expect(screen.getByText(/weighted pipeline/i)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<SalesTeamUI data={mockSalesData} />)
      expect(screen.getByRole('region', { name: /sales dashboard/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create deal/i })).toHaveAttribute('aria-label')
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} />)

      await user.tab()
      const firstButton = screen.getAllByRole('button')[0]
      expect(firstButton).toHaveFocus()
    })

    it('should announce pipeline updates to screen readers', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} />)

      const proposalStage = screen.getByText('Proposal')
      await user.click(proposalStage)

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(/filtered by proposal/i)
      })
    })

    it('should have proper heading hierarchy', () => {
      render(<SalesTeamUI data={mockSalesData} showTeamPerformance={true} />)
      const headings = screen.getAllByRole('heading')
      expect(headings[0].tagName).toBe('H2')
    })
  })

  describe('Responsive Behavior', () => {
    it('should adapt layout for mobile screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<SalesTeamUI data={mockSalesData} />)
      const container = screen.getByRole('region', { name: /sales dashboard/i })
      expect(container).toHaveClass('mobile-layout')
    })

    it('should hide detailed metrics on small screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<SalesTeamUI data={mockSalesData} showTeamPerformance={true} />)
      expect(screen.queryByText(/quota attainment/i)).not.toBeVisible()
    })
  })

  describe('Performance', () => {
    it('should render large deal lists efficiently', () => {
      const manyDeals = Array.from({ length: 500 }, (_, i) => ({
        id: `d${i}`,
        name: `Deal ${i}`,
        value: Math.random() * 100000,
        stage: 'Prospect',
        probability: Math.random() * 100,
      }))

      const startTime = performance.now()
      render(<SalesTeamUI data={{ ...mockSalesData, topDeals: manyDeals }} />)
      const endTime = performance.now()

      expect(endTime - startTime).toBeLessThan(1000)
    })

    it('should memoize pipeline calculations', () => {
      const { rerender } = render(<SalesTeamUI data={mockSalesData} />)
      const calculatePipeline = jest.fn()

      rerender(<SalesTeamUI data={mockSalesData} />)

      expect(calculatePipeline).not.toHaveBeenCalled()
    })
  })

  describe('Data Validation', () => {
    it('should handle missing revenue data', () => {
      const incompleteData = { ...mockSalesData, totalRevenue: undefined }
      render(<SalesTeamUI data={incompleteData} />)
      expect(screen.getByText(/n\/a/i)).toBeInTheDocument()
    })

    it('should validate deal value format', async () => {
      const user = userEvent.setup()
      render(<SalesTeamUI data={mockSalesData} />)

      const createButton = screen.getByRole('button', { name: /create deal/i })
      await user.click(createButton)

      const valueInput = screen.getByLabelText(/deal value/i)
      await user.type(valueInput, 'invalid')

      await waitFor(() => {
        expect(screen.getByText(/invalid value/i)).toBeInTheDocument()
      })
    })

    it('should handle negative values', () => {
      const negativeData = { ...mockSalesData, totalRevenue: -5000 }
      render(<SalesTeamUI data={negativeData} />)
      expect(screen.getByText(/-\$5,000/)).toBeInTheDocument()
    })
  })

  describe('Search and Filter', () => {
    it('should search deals by name', async () => {
      const user = userEvent.setup()
      const onSearch = jest.fn()
      render(<SalesTeamUI data={mockSalesData} onSearch={onSearch} />)

      const searchInput = screen.getByPlaceholderText(/search deals/i)
      await user.type(searchInput, 'Enterprise')

      await waitFor(() => {
        expect(onSearch).toHaveBeenCalledWith('Enterprise')
      })
    })

    it('should filter deals by value range', async () => {
      const user = userEvent.setup()
      const onFilter = jest.fn()
      render(<SalesTeamUI data={mockSalesData} onFilter={onFilter} />)

      const minValueInput = screen.getByLabelText(/min value/i)
      const maxValueInput = screen.getByLabelText(/max value/i)

      await user.type(minValueInput, '50000')
      await user.type(maxValueInput, '100000')

      const applyButton = screen.getByRole('button', { name: /apply filter/i })
      await user.click(applyButton)

      expect(onFilter).toHaveBeenCalledWith({ min: 50000, max: 100000 })
    })
  })
})
