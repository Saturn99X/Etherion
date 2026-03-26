import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock Apollo provider hook used by the component
jest.mock('@/components/apollo-provider', () => {
  return {
    useApolloClient: () => ({
      query: jest.fn().mockResolvedValue({ data: { getIntegrations: [] } }),
      mutate: jest.fn().mockResolvedValue({ data: { disconnectIntegration: true } }),
    }),
  }
})

// Prime auth store with a token containing tenant_id
jest.mock('@/lib/stores/auth-store', () => {
  const actual = jest.requireActual('@/lib/stores/auth-store')
  return {
    ...actual,
    useAuthStore: {
      getState: () => ({ user: { user_id: 'u1' }, token: 'header.' + btoa(JSON.stringify({ tenant_id: 123 })) + '.sig' }),
    },
  }
})

import { CredentialManager } from '@/components/credential-manager'

// Provide a mock fetch for OAuth start
const originalOpen = window.open

describe('CredentialManager OAuth Connect', () => {
  beforeEach(() => {
    ;(global as any).fetch = jest.fn().mockResolvedValue({ json: async () => ({ authorize_url: 'https://slack.com/oauth/test' }) })
    ;(window as any).open = jest.fn(() => ({ close: jest.fn() })) as any
  })
  afterEach(() => {
    ;(global as any).fetch = undefined
    window.open = originalOpen
    jest.restoreAllMocks()
  })

  it('starts OAuth for Slack and opens popup', async () => {
    render(<CredentialManager toolName="mcp_slack" />)

    // Should render connect button (OAuth-backed)
    const connectBtn = await screen.findByRole('button', { name: /connect via oauth|reconnect/i })
    fireEvent.click(connectBtn)

    await waitFor(() => {
      expect((global as any).fetch).toHaveBeenCalled()
      expect(window.open).toHaveBeenCalled()
    })
  })
})
