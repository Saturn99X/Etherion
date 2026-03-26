import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MarketingTeamUI } from '@/components/ui/agent-specific/marketing-team-ui'

const mockData = {
  campaigns: [
    { id: '1', name: 'Summer Sale', status: 'active', reach: 50000, conversions: 1250, budget: 10000 },
    { id: '2', name: 'Product Launch', status: 'scheduled', reach: 0, conversions: 0, budget: 15000 },
  ],
  metrics: {
    ctr: 3.5,
    cpc: 1.25,
    roas: 4.2,
    impressions: 125000,
    clicks: 4375,
    spend: 5468.75
  },
  channels: [
    { name: 'Google Ads', spend: 3000, conversions: 850 },
    { name: 'Facebook', spend: 2000, conversions: 400 },
  ],
  abTests: [
    { id: 't1', name: 'Homepage Banner', variantA: 45, variantB: 55, status: 'running' },
  ],
}

describe('MarketingTeamUI', () => {
  describe('Rendering', () => {
    it('should render without crashing', () => {
      render(<MarketingTeamUI data={mockData} />)
      expect(screen.getByText(/marketing dashboard/i)).toBeInTheDocument()
    })

    it('should display campaigns', () => {
      render(<MarketingTeamUI data={mockData} />)
      expect(screen.getByText('Summer Sale')).toBeInTheDocument()
      expect(screen.getByText('Product Launch')).toBeInTheDocument()
    })

    it('should show key metrics', () => {
      render(<MarketingTeamUI data={mockData} />)
      expect(screen.getByText(/3\.5%/)).toBeInTheDocument() // CTR
      expect(screen.getByText(/\$1\.25/)).toBeInTheDocument() // CPC
      expect(screen.getByText(/4\.2/)).toBeInTheDocument() // ROAS
    })

    it('should display loading state', () => {
      render(<MarketingTeamUI data={null} loading={true} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('should display error state', () => {
      const error = 'Failed to load marketing data'
      render(<MarketingTeamUI data={null} error={error} />)
      expect(screen.getByText(error)).toBeInTheDocument()
    })
  })

  describe('Campaign Builder', () => {
    it('should open campaign builder', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      const createBtn = screen.getByRole('button', { name: /create campaign/i })
      await user.click(createBtn)

      expect(screen.getByText(/campaign builder/i)).toBeInTheDocument()
    })

    it('should create new campaign', async () => {
      const user = userEvent.setup()
      const onCreate = jest.fn()
      render(<MarketingTeamUI data={mockData} onCampaignCreate={onCreate} />)

      const createBtn = screen.getByRole('button', { name: /create campaign/i })
      await user.click(createBtn)

      const nameInput = screen.getByLabelText(/campaign name/i)
      const budgetInput = screen.getByLabelText(/budget/i)

      await user.type(nameInput, 'New Campaign')
      await user.type(budgetInput, '5000')

      const saveBtn = screen.getByRole('button', { name: /save/i })
      await user.click(saveBtn)

      expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
        name: 'New Campaign',
        budget: 5000,
      }))
    })

    it('should validate campaign fields', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      const createBtn = screen.getByRole('button', { name: /create campaign/i })
      await user.click(createBtn)

      const saveBtn = screen.getByRole('button', { name: /save/i })
      await user.click(saveBtn)

      await waitFor(() => {
        expect(screen.getByText(/campaign name is required/i)).toBeInTheDocument()
      })
    })

    it('should select campaign channels', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      const createBtn = screen.getByRole('button', { name: /create campaign/i })
      await user.click(createBtn)

      const googleAdsCheckbox = screen.getByLabelText(/google ads/i)
      const facebookCheckbox = screen.getByLabelText(/facebook/i)

      await user.click(googleAdsCheckbox)
      await user.click(facebookCheckbox)

      expect(googleAdsCheckbox).toBeChecked()
      expect(facebookCheckbox).toBeChecked()
    })
  })

  describe('A/B Testing', () => {
    it('should display A/B tests', () => {
      render(<MarketingTeamUI data={mockData} showABTests={true} />)
      expect(screen.getByText(/a\/b testing/i)).toBeInTheDocument()
      expect(screen.getByText('Homepage Banner')).toBeInTheDocument()
    })

    it('should show test results', () => {
      render(<MarketingTeamUI data={mockData} showABTests={true} />)
      expect(screen.getByText('45')).toBeInTheDocument() // Variant A
      expect(screen.getByText('55')).toBeInTheDocument() // Variant B
    })

    it('should create new A/B test', async () => {
      const user = userEvent.setup()
      const onTestCreate = jest.fn()
      render(<MarketingTeamUI data={mockData} showABTests={true} onABTestCreate={onTestCreate} />)

      const createBtn = screen.getByRole('button', { name: /create test/i })
      await user.click(createBtn)

      const nameInput = screen.getByLabelText(/test name/i)
      await user.type(nameInput, 'Button Color Test')

      const startBtn = screen.getByRole('button', { name: /start test/i })
      await user.click(startBtn)

      expect(onTestCreate).toHaveBeenCalled()
    })

    it('should declare test winner', async () => {
      const user = userEvent.setup()
      const onDeclareWinner = jest.fn()
      render(<MarketingTeamUI data={mockData} showABTests={true} onDeclareWinner={onDeclareWinner} />)

      const variantBButton = screen.getByRole('button', { name: /declare variant b winner/i })
      await user.click(variantBButton)

      expect(onDeclareWinner).toHaveBeenCalledWith('t1', 'B')
    })
  })

  describe('Channel Performance', () => {
    it('should display channel breakdown', () => {
      render(<MarketingTeamUI data={mockData} showChannels={true} />)
      expect(screen.getByText('Google Ads')).toBeInTheDocument()
      expect(screen.getByText('Facebook')).toBeInTheDocument()
    })

    it('should show spend per channel', () => {
      render(<MarketingTeamUI data={mockData} showChannels={true} />)
      expect(screen.getByText(/\$3,000/)).toBeInTheDocument()
      expect(screen.getByText(/\$2,000/)).toBeInTheDocument()
    })

    it('should calculate channel ROI', () => {
      render(<MarketingTeamUI data={mockData} showChannels={true} />)
      // Google Ads: 850 conversions at avg $25 = $21,250 / $3,000 = 7.08x
      expect(screen.getByText(/roi/i)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<MarketingTeamUI data={mockData} />)
      expect(screen.getByRole('region', { name: /marketing dashboard/i })).toBeInTheDocument()
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      await user.tab()
      const firstButton = screen.getAllByRole('button')[0]
      expect(firstButton).toHaveFocus()
    })

    it('should announce updates to screen readers', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      const createBtn = screen.getByRole('button', { name: /create campaign/i })
      await user.click(createBtn)

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(/campaign builder opened/i)
      })
    })
  })

  describe('Responsive Behavior', () => {
    it('should adapt for mobile screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<MarketingTeamUI data={mockData} />)
      const container = screen.getByRole('region', { name: /marketing dashboard/i })
      expect(container).toHaveClass('mobile-layout')
    })

    it('should hide detailed metrics on small screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<MarketingTeamUI data={mockData} />)
      expect(screen.queryByText(/advanced metrics/i)).not.toBeVisible()
    })
  })

  describe('Performance', () => {
    it('should render large campaign lists efficiently', () => {
      const manyCampaigns = Array.from({ length: 200 }, (_, i) => ({
        id: `c${i}`,
        name: `Campaign ${i}`,
        status: 'active',
        reach: 10000,
        conversions: 250,
        budget: 5000,
      }))

      const startTime = performance.now()
      render(<MarketingTeamUI data={{ ...mockData, campaigns: manyCampaigns }} />)
      const endTime = performance.now()

      expect(endTime - startTime).toBeLessThan(1000)
    })
  })

  describe('Data Validation', () => {
    it('should handle missing campaign data', () => {
      const incompleteData = { ...mockData, campaigns: undefined }
      render(<MarketingTeamUI data={incompleteData} />)
      expect(screen.getByText(/no campaigns/i)).toBeInTheDocument()
    })

    it('should format currency correctly', () => {
      render(<MarketingTeamUI data={mockData} />)
      expect(screen.getByText(/\$1\.25/)).toBeInTheDocument()
    })
  })

  describe('Filtering and Sorting', () => {
    it('should filter campaigns by status', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      const statusFilter = screen.getByRole('combobox', { name: /status/i })
      await user.selectOptions(statusFilter, 'active')

      await waitFor(() => {
        expect(screen.getByText('Summer Sale')).toBeInTheDocument()
        expect(screen.queryByText('Product Launch')).not.toBeInTheDocument()
      })
    })

    it('should sort campaigns by performance', async () => {
      const user = userEvent.setup()
      render(<MarketingTeamUI data={mockData} />)

      const sortButton = screen.getByRole('button', { name: /sort/i })
      await user.click(sortButton)

      const conversionsOption = screen.getByText(/conversions/i)
      await user.click(conversionsOption)

      await waitFor(() => {
        const campaigns = screen.getAllByRole('listitem')
        expect(campaigns[0]).toHaveTextContent('Summer Sale')
      })
    })
  })
})
