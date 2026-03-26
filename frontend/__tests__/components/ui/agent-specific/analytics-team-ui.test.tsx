import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AnalyticsTeamUI } from '@/components/ui/agent-specific/analytics-team-ui'

// Mock data
const mockAnalyticsData = {
  pageViews: 125000,
  uniqueVisitors: 45000,
  bounceRate: 42.5,
  avgSessionDuration: 245,
  conversionRate: 3.2,
  trafficSources: [
    { source: 'Organic Search', visitors: 20000, percentage: 44.4 },
    { source: 'Direct', visitors: 15000, percentage: 33.3 },
    { source: 'Social Media', visitors: 7000, percentage: 15.6 },
    { source: 'Referral', visitors: 3000, percentage: 6.7 },
  ],
  topPages: [
    { url: '/products', views: 35000, avgTime: 180 },
    { url: '/blog', views: 28000, avgTime: 320 },
    { url: '/pricing', views: 22000, avgTime: 150 },
  ],
  userBehavior: {
    newUsers: 30000,
    returningUsers: 15000,
    deviceBreakdown: {
      desktop: 25000,
      mobile: 18000,
      tablet: 2000,
    },
  },
  timeSeriesData: [
    { date: '2024-01-01', visits: 1200, conversions: 38 },
    { date: '2024-01-02', visits: 1350, conversions: 42 },
    { date: '2024-01-03', visits: 1180, conversions: 35 },
    { date: '2024-01-04', visits: 1420, conversions: 48 },
    { date: '2024-01-05', visits: 1590, conversions: 52 },
  ],
  heatmapData: {
    clickData: [
      { x: 100, y: 200, clicks: 45 },
      { x: 300, y: 150, clicks: 78 },
    ],
    scrollDepth: {
      '0-25%': 100,
      '25-50%': 85,
      '50-75%': 60,
      '75-100%': 35,
    },
  },
}

const mockFunnelData = {
  steps: [
    { name: 'Landing Page', visitors: 10000, dropoff: 0 },
    { name: 'Product Page', visitors: 7500, dropoff: 2500 },
    { name: 'Add to Cart', visitors: 4200, dropoff: 3300 },
    { name: 'Checkout', visitors: 2800, dropoff: 1400 },
    { name: 'Purchase', visitors: 2100, dropoff: 700 },
  ],
}

describe('AnalyticsTeamUI', () => {
  describe('Rendering', () => {
    it('should render without crashing', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)
      expect(screen.getByText(/analytics dashboard/i)).toBeInTheDocument()
    })

    it('should display key metrics', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      expect(screen.getByText(/page views/i)).toBeInTheDocument()
      expect(screen.getByText('125,000')).toBeInTheDocument()
      expect(screen.getByText(/unique visitors/i)).toBeInTheDocument()
      expect(screen.getByText('45,000')).toBeInTheDocument()
      expect(screen.getByText(/bounce rate/i)).toBeInTheDocument()
      expect(screen.getByText('42.5%')).toBeInTheDocument()
    })

    it('should render traffic sources chart', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)
      expect(screen.getByText('Organic Search')).toBeInTheDocument()
      expect(screen.getByText('44.4%')).toBeInTheDocument()
    })

    it('should display loading state', () => {
      render(<AnalyticsTeamUI data={null} loading={true} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('should display error state', () => {
      const error = 'Failed to load analytics data'
      render(<AnalyticsTeamUI data={null} error={error} />)
      expect(screen.getByText(error)).toBeInTheDocument()
    })
  })

  describe('Time Range Selection', () => {
    it('should allow selecting different time ranges', async () => {
      const user = userEvent.setup()
      const onTimeRangeChange = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onTimeRangeChange={onTimeRangeChange} />)

      const timeRangeSelector = screen.getByRole('combobox', { name: /time range/i })
      await user.selectOptions(timeRangeSelector, 'last-7-days')

      expect(onTimeRangeChange).toHaveBeenCalledWith('last-7-days')
    })

    it('should support custom date range', async () => {
      const user = userEvent.setup()
      const onCustomDateRange = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onCustomDateRange={onCustomDateRange} />)

      const customRangeButton = screen.getByRole('button', { name: /custom range/i })
      await user.click(customRangeButton)

      const startDateInput = screen.getByLabelText(/start date/i)
      const endDateInput = screen.getByLabelText(/end date/i)

      await user.type(startDateInput, '2024-01-01')
      await user.type(endDateInput, '2024-01-31')

      const applyButton = screen.getByRole('button', { name: /apply/i })
      await user.click(applyButton)

      expect(onCustomDateRange).toHaveBeenCalledWith({
        start: '2024-01-01',
        end: '2024-01-31',
      })
    })

    it('should show comparison mode', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} enableComparison={true} />)

      const compareButton = screen.getByRole('button', { name: /compare/i })
      await user.click(compareButton)

      expect(screen.getByText(/compare with previous period/i)).toBeInTheDocument()
    })
  })

  describe('Data Visualization', () => {
    it('should render time series chart', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} showTimeSeriesChart={true} />)
      expect(screen.getByRole('img', { name: /time series chart/i })).toBeInTheDocument()
    })

    it('should toggle between different chart types', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} showTimeSeriesChart={true} />)

      const chartTypeSelector = screen.getByRole('combobox', { name: /chart type/i })
      await user.selectOptions(chartTypeSelector, 'bar')

      expect(chartTypeSelector).toHaveValue('bar')
    })

    it('should display funnel visualization', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} funnelData={mockFunnelData} />)
      expect(screen.getByText(/conversion funnel/i)).toBeInTheDocument()
      expect(screen.getByText('Landing Page')).toBeInTheDocument()
      expect(screen.getByText('10,000')).toBeInTheDocument()
    })

    it('should show heatmap when enabled', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} showHeatmap={true} />)
      expect(screen.getByText(/click heatmap/i)).toBeInTheDocument()
    })

    it('should render pie chart for device breakdown', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} showDeviceBreakdown={true} />)
      expect(screen.getByText(/device breakdown/i)).toBeInTheDocument()
      expect(screen.getByText('Desktop')).toBeInTheDocument()
      expect(screen.getByText('Mobile')).toBeInTheDocument()
    })
  })

  describe('Filtering and Segmentation', () => {
    it('should filter by traffic source', async () => {
      const user = userEvent.setup()
      const onFilterChange = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onFilterChange={onFilterChange} />)

      const sourceFilter = screen.getByRole('combobox', { name: /traffic source/i })
      await user.selectOptions(sourceFilter, 'Organic Search')

      expect(onFilterChange).toHaveBeenCalledWith({ source: 'Organic Search' })
    })

    it('should segment by user type', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      const segmentButtons = screen.getAllByRole('button', { name: /user type/i })
      const newUsersButton = segmentButtons.find(btn => btn.textContent?.includes('New'))

      if (newUsersButton) {
        await user.click(newUsersButton)
        expect(newUsersButton).toHaveAttribute('aria-pressed', 'true')
      }
    })

    it('should apply multiple filters simultaneously', async () => {
      const user = userEvent.setup()
      const onFilterChange = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onFilterChange={onFilterChange} />)

      const sourceFilter = screen.getByRole('combobox', { name: /traffic source/i })
      const deviceFilter = screen.getByRole('combobox', { name: /device/i })

      await user.selectOptions(sourceFilter, 'Organic Search')
      await user.selectOptions(deviceFilter, 'mobile')

      expect(onFilterChange).toHaveBeenCalledWith({
        source: 'Organic Search',
        device: 'mobile',
      })
    })
  })

  describe('Top Pages Analysis', () => {
    it('should display top pages list', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)
      expect(screen.getByText('/products')).toBeInTheDocument()
      expect(screen.getByText('/blog')).toBeInTheDocument()
      expect(screen.getByText('/pricing')).toBeInTheDocument()
    })

    it('should sort top pages by different metrics', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      const sortButton = screen.getByRole('button', { name: /sort by/i })
      await user.click(sortButton)

      const avgTimeOption = screen.getByText(/average time/i)
      await user.click(avgTimeOption)

      await waitFor(() => {
        const pages = screen.getAllByRole('listitem')
        expect(pages[0]).toHaveTextContent('/blog')
      })
    })

    it('should show page details on click', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      const pageLink = screen.getByText('/products')
      await user.click(pageLink)

      await waitFor(() => {
        expect(screen.getByText(/page details/i)).toBeInTheDocument()
      })
    })
  })

  describe('Real-time Analytics', () => {
    it('should display real-time visitor count', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} enableRealTime={true} />)
      expect(screen.getByText(/active visitors/i)).toBeInTheDocument()
    })

    it('should update real-time data periodically', async () => {
      jest.useFakeTimers()
      const onRefresh = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} enableRealTime={true} onRefresh={onRefresh} />)

      jest.advanceTimersByTime(5000)

      await waitFor(() => {
        expect(onRefresh).toHaveBeenCalled()
      })

      jest.useRealTimers()
    })

    it('should show real-time event stream', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} enableRealTime={true} showEventStream={true} />)
      expect(screen.getByText(/event stream/i)).toBeInTheDocument()
    })
  })

  describe('Export Functionality', () => {
    it('should export data as CSV', async () => {
      const user = userEvent.setup()
      const onExport = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onExport={onExport} />)

      const exportButton = screen.getByRole('button', { name: /export/i })
      await user.click(exportButton)

      const csvOption = screen.getByText(/csv/i)
      await user.click(csvOption)

      expect(onExport).toHaveBeenCalledWith('csv', mockAnalyticsData)
    })

    it('should export data as PDF', async () => {
      const user = userEvent.setup()
      const onExport = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onExport={onExport} />)

      const exportButton = screen.getByRole('button', { name: /export/i })
      await user.click(exportButton)

      const pdfOption = screen.getByText(/pdf/i)
      await user.click(pdfOption)

      expect(onExport).toHaveBeenCalledWith('pdf', mockAnalyticsData)
    })

    it('should export with selected date range', async () => {
      const user = userEvent.setup()
      const onExport = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onExport={onExport} />)

      const timeRangeSelector = screen.getByRole('combobox', { name: /time range/i })
      await user.selectOptions(timeRangeSelector, 'last-30-days')

      const exportButton = screen.getByRole('button', { name: /export/i })
      await user.click(exportButton)

      const csvOption = screen.getByText(/csv/i)
      await user.click(csvOption)

      expect(onExport).toHaveBeenCalledWith('csv', mockAnalyticsData, 'last-30-days')
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)
      expect(screen.getByRole('region', { name: /analytics dashboard/i })).toBeInTheDocument()
      expect(screen.getByRole('combobox', { name: /time range/i })).toHaveAttribute('aria-label')
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      await user.tab()
      const firstButton = screen.getAllByRole('button')[0]
      expect(firstButton).toHaveFocus()
    })

    it('should announce data updates to screen readers', async () => {
      const { rerender } = render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      const updatedData = { ...mockAnalyticsData, pageViews: 150000 }
      rerender(<AnalyticsTeamUI data={updatedData} />)

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(/data updated/i)
      })
    })

    it('should have proper color contrast for charts', () => {
      render(<AnalyticsTeamUI data={mockAnalyticsData} showTimeSeriesChart={true} />)
      const chart = screen.getByRole('img', { name: /time series chart/i })
      expect(chart).toHaveAttribute('aria-describedby')
    })
  })

  describe('Responsive Behavior', () => {
    it('should adapt layout for mobile screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<AnalyticsTeamUI data={mockAnalyticsData} />)
      const container = screen.getByRole('region', { name: /analytics dashboard/i })
      expect(container).toHaveClass('mobile-layout')
    })

    it('should show simplified metrics on mobile', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<AnalyticsTeamUI data={mockAnalyticsData} />)
      expect(screen.queryByText(/advanced metrics/i)).not.toBeVisible()
    })

    it('should use responsive charts', () => {
      global.innerWidth = 768
      global.dispatchEvent(new Event('resize'))

      render(<AnalyticsTeamUI data={mockAnalyticsData} showTimeSeriesChart={true} />)
      const chart = screen.getByRole('img', { name: /time series chart/i })
      expect(chart).toHaveClass('responsive-chart')
    })
  })

  describe('Performance', () => {
    it('should render large datasets efficiently', () => {
      const largeDataset = {
        ...mockAnalyticsData,
        timeSeriesData: Array.from({ length: 365 }, (_, i) => ({
          date: `2024-01-${i + 1}`,
          visits: Math.floor(Math.random() * 2000),
          conversions: Math.floor(Math.random() * 60),
        })),
      }

      const startTime = performance.now()
      render(<AnalyticsTeamUI data={largeDataset} />)
      const endTime = performance.now()

      expect(endTime - startTime).toBeLessThan(1000)
    })

    it('should debounce filter changes', async () => {
      const onFilterChange = jest.fn()
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onFilterChange={onFilterChange} />)

      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'test query')

      await waitFor(() => {
        expect(onFilterChange).toHaveBeenCalledTimes(1)
      })
    })

    it('should virtualize long lists', () => {
      const manyPages = Array.from({ length: 1000 }, (_, i) => ({
        url: `/page-${i}`,
        views: Math.floor(Math.random() * 50000),
        avgTime: Math.floor(Math.random() * 300),
      }))

      render(<AnalyticsTeamUI data={{ ...mockAnalyticsData, topPages: manyPages }} />)

      const visibleItems = screen.getAllByRole('listitem')
      expect(visibleItems.length).toBeLessThan(100) // Should not render all 1000
    })
  })

  describe('Data Validation', () => {
    it('should handle missing data gracefully', () => {
      const incompleteData = { ...mockAnalyticsData, pageViews: undefined }
      render(<AnalyticsTeamUI data={incompleteData} />)
      expect(screen.getByText(/n\/a/i)).toBeInTheDocument()
    })

    it('should validate percentage values', () => {
      const invalidData = { ...mockAnalyticsData, bounceRate: 150 }
      render(<AnalyticsTeamUI data={invalidData} />)
      expect(screen.getByText(/invalid data/i)).toBeInTheDocument()
    })

    it('should handle zero values correctly', () => {
      const zeroData = { ...mockAnalyticsData, uniqueVisitors: 0 }
      render(<AnalyticsTeamUI data={zeroData} />)
      expect(screen.getByText('0')).toBeInTheDocument()
      expect(screen.queryByText(/n\/a/i)).not.toBeInTheDocument()
    })
  })

  describe('Drill-down Capabilities', () => {
    it('should drill down into traffic source details', async () => {
      const user = userEvent.setup()
      const onDrillDown = jest.fn()
      render(<AnalyticsTeamUI data={mockAnalyticsData} onDrillDown={onDrillDown} />)

      const organicSearchSource = screen.getByText('Organic Search')
      await user.click(organicSearchSource)

      expect(onDrillDown).toHaveBeenCalledWith('trafficSource', 'Organic Search')
    })

    it('should show breadcrumb navigation for drill-downs', async () => {
      const user = userEvent.setup()
      render(<AnalyticsTeamUI data={mockAnalyticsData} />)

      const organicSearchSource = screen.getByText('Organic Search')
      await user.click(organicSearchSource)

      await waitFor(() => {
        expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument()
      })
    })
  })
})
