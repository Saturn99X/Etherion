import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

jest.mock('@/components/apollo-provider', () => {
  return {
    useApolloClient: () => ({
      query: jest.fn().mockImplementation(({ query }) => {
        // Return a minimal job history payload with one job that has threadId and one without
        return Promise.resolve({
          data: {
            getJobHistory: {
              jobs: [
                { id: 'job-1', goal: 'A', status: 'completed', createdAt: new Date().toISOString(), duration: '1s', totalCost: '$0.01', modelUsed: 'gpt', threadId: 't-1' },
                { id: 'job-2', goal: 'B', status: 'completed', createdAt: new Date().toISOString(), duration: '1s', totalCost: '$0.01', modelUsed: 'gpt', threadId: null },
              ],
              totalCount: 2,
              pageInfo: { hasNextPage: false, hasPreviousPage: false },
            },
          },
        })
      }),
    }),
  }
})

import { JobsDashboard } from '@/components/jobs-dashboard'

describe('JobsDashboard deep-link to Interact', () => {
  it('enables Open Chat only when threadId exists and routes with thread param', async () => {
    const { useRouter } = require('next/navigation')
    const router = useRouter()

    render(<JobsDashboard />)

    // Wait for jobs to load
    await waitFor(() => {
      expect(screen.getByText('Job History (2 total)')).toBeInTheDocument()
    })

    const allButtons = screen.getAllByRole('button', { name: /open chat/i })
    expect(allButtons.length).toBe(2)

    // First job has threadId; second doesn't
    // The first Open Chat should be enabled
    expect(allButtons[0]).not.toBeDisabled()
    fireEvent.click(allButtons[0])
    expect(router.push).toHaveBeenCalledWith(expect.stringContaining('/interact?thread=t-1'))

    // The second Open Chat should be disabled
    expect(allButtons[1]).toBeDisabled()
  })
})
