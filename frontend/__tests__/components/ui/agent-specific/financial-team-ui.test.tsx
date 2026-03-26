import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FinancialTeamUI } from '@/components/ui/agent-specific/financial-team-ui'

// Mock data
const mockFinancialData = {
  revenue: 150000,
  expenses: 95000,
  profit: 55000,
  roi: 0.58,
  cashFlow: [
    { month: 'Jan', income: 12000, expenses: 8000 },
    { month: 'Feb', income: 15000, expenses: 9000 },
    { month: 'Mar', income: 18000, expenses: 10000 },
  ],
  budgetCategories: [
    { category: 'Marketing', allocated: 30000, spent: 25000 },
    { category: 'Operations', allocated: 40000, spent: 38000 },
    { category: 'Development', allocated: 50000, spent: 32000 },
  ],
}

const mockRiskAssessment = {
  overallRisk: 'medium',
  riskFactors: [
    { factor: 'Market Volatility', level: 'high', score: 7.5 },
    { factor: 'Cash Flow', level: 'low', score: 2.3 },
    { factor: 'Debt Ratio', level: 'medium', score: 5.1 },
  ],
}

describe('FinancialTeamUI', () => {
  describe('Rendering', () => {
    it('should render without crashing', () => {
      render(<FinancialTeamUI data={mockFinancialData} />)
      expect(screen.getByText(/financial dashboard/i)).toBeInTheDocument()
    })

    it('should display financial metrics correctly', () => {
      render(<FinancialTeamUI data={mockFinancialData} />)

      expect(screen.getByText(/revenue/i)).toBeInTheDocument()
      expect(screen.getByText(/\$150,000/)).toBeInTheDocument()
      expect(screen.getByText(/expenses/i)).toBeInTheDocument()
      expect(screen.getByText(/\$95,000/)).toBeInTheDocument()
      expect(screen.getByText(/profit/i)).toBeInTheDocument()
      expect(screen.getByText(/\$55,000/)).toBeInTheDocument()
    })

    it('should render ROI calculator when provided', () => {
      render(<FinancialTeamUI data={mockFinancialData} showROICalculator={true} />)
      expect(screen.getByText(/roi calculator/i)).toBeInTheDocument()
      expect(screen.getByText(/58%/)).toBeInTheDocument()
    })

    it('should render risk heat map when risk data is provided', () => {
      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)
      expect(screen.getByText(/risk assessment/i)).toBeInTheDocument()
      expect(screen.getByText(/market volatility/i)).toBeInTheDocument()
    })

    it('should display loading state when data is loading', () => {
      render(<FinancialTeamUI data={null} loading={true} />)
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })

    it('should display error state when error occurs', () => {
      const error = 'Failed to load financial data'
      render(<FinancialTeamUI data={null} error={error} />)
      expect(screen.getByText(error)).toBeInTheDocument()
    })
  })

  describe('Financial Dashboard Interactions', () => {
    it('should allow switching between different time periods', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} />)

      const monthlyButton = screen.getByRole('button', { name: /monthly/i })
      const quarterlyButton = screen.getByRole('button', { name: /quarterly/i })

      await user.click(quarterlyButton)
      expect(quarterlyButton).toHaveClass('active')

      await user.click(monthlyButton)
      expect(monthlyButton).toHaveClass('active')
    })

    it('should filter budget categories', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} />)

      const filterInput = screen.getByPlaceholderText(/filter categories/i)
      await user.type(filterInput, 'Marketing')

      await waitFor(() => {
        expect(screen.getByText('Marketing')).toBeInTheDocument()
        expect(screen.queryByText('Operations')).not.toBeInTheDocument()
      })
    })

    it('should export financial report when export button is clicked', async () => {
      const onExport = jest.fn()
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} onExport={onExport} />)

      const exportButton = screen.getByRole('button', { name: /export/i })
      await user.click(exportButton)

      expect(onExport).toHaveBeenCalledWith(mockFinancialData)
    })
  })

  describe('ROI Calculator', () => {
    it('should calculate ROI based on input values', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} showROICalculator={true} />)

      const investmentInput = screen.getByLabelText(/investment amount/i)
      const returnInput = screen.getByLabelText(/return amount/i)

      await user.clear(investmentInput)
      await user.type(investmentInput, '10000')

      await user.clear(returnInput)
      await user.type(returnInput, '15000')

      await waitFor(() => {
        expect(screen.getByText(/50%/)).toBeInTheDocument()
      })
    })

    it('should show error for invalid ROI inputs', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} showROICalculator={true} />)

      const investmentInput = screen.getByLabelText(/investment amount/i)
      await user.clear(investmentInput)
      await user.type(investmentInput, '-1000')

      await waitFor(() => {
        expect(screen.getByText(/invalid investment amount/i)).toBeInTheDocument()
      })
    })

    it('should reset ROI calculator', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} showROICalculator={true} />)

      const investmentInput = screen.getByLabelText(/investment amount/i)
      const resetButton = screen.getByRole('button', { name: /reset/i })

      await user.type(investmentInput, '10000')
      await user.click(resetButton)

      expect(investmentInput).toHaveValue('')
    })
  })

  describe('Risk Heat Map', () => {
    it('should display risk factors with correct severity levels', () => {
      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)

      expect(screen.getByText('Market Volatility')).toBeInTheDocument()
      expect(screen.getByText(/high/i)).toBeInTheDocument()
      expect(screen.getByText('Cash Flow')).toBeInTheDocument()
      expect(screen.getByText(/low/i)).toBeInTheDocument()
    })

    it('should show overall risk level', () => {
      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)
      expect(screen.getByText(/overall risk: medium/i)).toBeInTheDocument()
    })

    it('should allow filtering risk factors by severity', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)

      const highRiskFilter = screen.getByRole('button', { name: /high risk only/i })
      await user.click(highRiskFilter)

      await waitFor(() => {
        expect(screen.getByText('Market Volatility')).toBeInTheDocument()
        expect(screen.queryByText('Cash Flow')).not.toBeInTheDocument()
      })
    })

    it('should show risk details on hover', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)

      const riskFactor = screen.getByText('Market Volatility')
      await user.hover(riskFactor)

      await waitFor(() => {
        expect(screen.getByText(/score: 7.5/i)).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<FinancialTeamUI data={mockFinancialData} />)

      expect(screen.getByRole('region', { name: /financial dashboard/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /export/i })).toHaveAttribute('aria-label')
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} showROICalculator={true} />)

      await user.tab()
      expect(screen.getByRole('button', { name: /monthly/i })).toHaveFocus()

      await user.tab()
      expect(screen.getByRole('button', { name: /quarterly/i })).toHaveFocus()
    })

    it('should have proper heading hierarchy', () => {
      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)

      const headings = screen.getAllByRole('heading')
      expect(headings[0]).toHaveTextContent(/financial dashboard/i)
      expect(headings[0].tagName).toBe('H2')
    })

    it('should announce updates to screen readers', async () => {
      const user = userEvent.setup()
      render(<FinancialTeamUI data={mockFinancialData} />)

      const quarterlyButton = screen.getByRole('button', { name: /quarterly/i })
      await user.click(quarterlyButton)

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(/view updated/i)
      })
    })
  })

  describe('Responsive Behavior', () => {
    it('should adapt layout for mobile screens', () => {
      global.innerWidth = 375
      global.dispatchEvent(new Event('resize'))

      render(<FinancialTeamUI data={mockFinancialData} />)

      const container = screen.getByRole('region', { name: /financial dashboard/i })
      expect(container).toHaveClass('mobile-layout')
    })

    it('should show full features on desktop', () => {
      global.innerWidth = 1920
      global.dispatchEvent(new Event('resize'))

      render(<FinancialTeamUI data={mockFinancialData} riskAssessment={mockRiskAssessment} />)

      expect(screen.getByText(/roi calculator/i)).toBeVisible()
      expect(screen.getByText(/risk assessment/i)).toBeVisible()
    })
  })

  describe('Data Validation', () => {
    it('should handle missing revenue data gracefully', () => {
      const incompleteData = { ...mockFinancialData, revenue: undefined }
      render(<FinancialTeamUI data={incompleteData} />)

      expect(screen.getByText(/n\/a/i)).toBeInTheDocument()
    })

    it('should handle negative values correctly', () => {
      const negativeData = { ...mockFinancialData, profit: -5000 }
      render(<FinancialTeamUI data={negativeData} />)

      expect(screen.getByText(/-\$5,000/)).toBeInTheDocument()
      expect(screen.getByText(/-\$5,000/)).toHaveClass('negative')
    })

    it('should format large numbers with proper separators', () => {
      const largeData = { ...mockFinancialData, revenue: 1500000 }
      render(<FinancialTeamUI data={largeData} />)

      expect(screen.getByText(/\$1,500,000/)).toBeInTheDocument()
    })
  })

  describe('Performance', () => {
    it('should not re-render unnecessarily', () => {
      const { rerender } = render(<FinancialTeamUI data={mockFinancialData} />)
      const renderCount = jest.fn()

      // Mock component to track renders
      jest.spyOn(React, 'createElement').mockImplementation(renderCount)

      rerender(<FinancialTeamUI data={mockFinancialData} />)

      // Same props should not trigger re-render
      expect(renderCount).toHaveBeenCalledTimes(0)
    })

    it('should handle large datasets efficiently', () => {
      const largeDataset = {
        ...mockFinancialData,
        cashFlow: Array.from({ length: 100 }, (_, i) => ({
          month: `Month ${i}`,
          income: Math.random() * 10000,
          expenses: Math.random() * 8000,
        })),
      }

      const startTime = performance.now()
      render(<FinancialTeamUI data={largeDataset} />)
      const endTime = performance.now()

      expect(endTime - startTime).toBeLessThan(1000) // Should render in less than 1 second
    })
  })
})
