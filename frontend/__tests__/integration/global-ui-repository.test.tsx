import React from 'react'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MockedProvider } from '@apollo/client/testing'
import { GlobalUIRepository } from '@/components/ui/global-ui-repository'

// Mock WebSocket
class MockWebSocket {
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(public url: string) {
    setTimeout(() => {
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 0)
  }

  send(data: string) {
    // Mock send
  }

  close() {
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  }
}

global.WebSocket = MockWebSocket as any

// Mock GraphQL queries
const MOCK_UI_EVENTS_SUBSCRIPTION = {
  request: {
    query: require('@/graphql/subscriptions').UI_EVENTS_SUBSCRIPTION,
  },
  result: {
    data: {
      uiEvents: {
        id: 'event1',
        type: 'COMPONENT_TRIGGER',
        component: 'financial-team-ui',
        data: { metric: 'revenue', value: 150000 },
        timestamp: '2024-01-15T10:00:00Z',
      },
    },
  },
}

const MOCK_COMPONENT_REGISTRY_QUERY = {
  request: {
    query: require('@/graphql/queries').GET_COMPONENT_REGISTRY,
  },
  result: {
    data: {
      componentRegistry: [
        { id: 'c1', name: 'financial-team-ui', version: '1.0.0', status: 'active' },
        { id: 'c2', name: 'content-team-ui', version: '1.0.0', status: 'active' },
        { id: 'c3', name: 'analytics-team-ui', version: '1.0.0', status: 'active' },
      ],
    },
  },
}

describe('GlobalUIRepository Integration Tests', () => {
  describe('Initialization', () => {
    it('should initialize repository and load component registry', async () => {
      render(
        <MockedProvider mocks={[MOCK_COMPONENT_REGISTRY_QUERY]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/repository initialized/i)).toBeInTheDocument()
      })
    })

    it('should establish WebSocket connection on mount', async () => {
      const { container } = render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(container.querySelector('[data-websocket-status="connected"]')).toBeTruthy()
      })
    })

    it('should setup GraphQL subscriptions', async () => {
      render(
        <MockedProvider mocks={[MOCK_UI_EVENTS_SUBSCRIPTION]} addTypename={false}>
          <GlobalUIRepository enableSubscriptions={true} />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/subscriptions active/i)).toBeInTheDocument()
      })
    })

    it('should handle initialization errors gracefully', async () => {
      const errorMock = {
        request: MOCK_COMPONENT_REGISTRY_QUERY.request,
        error: new Error('Failed to load registry'),
      }

      render(
        <MockedProvider mocks={[errorMock]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/initialization error/i)).toBeInTheDocument()
      })
    })
  })

  describe('Real-Time UI Updates', () => {
    it('should receive and process UI events via WebSocket', async () => {
      const onUIEvent = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUIEvent={onUIEvent} />
        </MockedProvider>
      )

      // Simulate WebSocket message
      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onmessage) {
          ws.onmessage(new MessageEvent('message', {
            data: JSON.stringify({
              type: 'UI_UPDATE',
              component: 'financial-team-ui',
              data: { revenue: 200000 }
            })
          }))
        }
      })

      await waitFor(() => {
        expect(onUIEvent).toHaveBeenCalledWith(expect.objectContaining({
          type: 'UI_UPDATE',
          component: 'financial-team-ui',
        }))
      })
    })

    it('should trigger component updates based on GraphQL subscriptions', async () => {
      const onComponentUpdate = jest.fn()

      render(
        <MockedProvider mocks={[MOCK_UI_EVENTS_SUBSCRIPTION]} addTypename={false}>
          <GlobalUIRepository
            enableSubscriptions={true}
            onComponentUpdate={onComponentUpdate}
          />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(onComponentUpdate).toHaveBeenCalledWith('financial-team-ui', expect.any(Object))
      }, { timeout: 3000 })
    })

    it('should debounce rapid UI updates', async () => {
      const onUIEvent = jest.fn()
      jest.useFakeTimers()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUIEvent={onUIEvent} debounceMs={500} />
        </MockedProvider>
      )

      // Send multiple events rapidly
      await act(async () => {
        for (let i = 0; i < 10; i++) {
          const ws = (global.WebSocket as any).instances?.[0]
          if (ws && ws.onmessage) {
            ws.onmessage(new MessageEvent('message', {
              data: JSON.stringify({ type: 'UI_UPDATE', data: { count: i } })
            }))
          }
        }
      })

      act(() => {
        jest.advanceTimersByTime(500)
      })

      await waitFor(() => {
        // Should only call once after debounce
        expect(onUIEvent).toHaveBeenCalledTimes(1)
      })

      jest.useRealTimers()
    })

    it('should handle WebSocket reconnection', async () => {
      const { container } = render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      // Simulate disconnect
      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onclose) {
          ws.onclose(new CloseEvent('close'))
        }
      })

      await waitFor(() => {
        expect(container.querySelector('[data-websocket-status="reconnecting"]')).toBeTruthy()
      })

      // Should reconnect
      await waitFor(() => {
        expect(container.querySelector('[data-websocket-status="connected"]')).toBeTruthy()
      }, { timeout: 5000 })
    })
  })

  describe('Component Loading and Registry', () => {
    it('should dynamically load components on demand', async () => {
      render(
        <MockedProvider mocks={[MOCK_COMPONENT_REGISTRY_QUERY]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/3 components loaded/i)).toBeInTheDocument()
      })
    })

    it('should validate component versions before loading', async () => {
      const outdatedMock = {
        request: MOCK_COMPONENT_REGISTRY_QUERY.request,
        result: {
          data: {
            componentRegistry: [
              { id: 'c1', name: 'financial-team-ui', version: '0.5.0', status: 'outdated' },
            ],
          },
        },
      }

      render(
        <MockedProvider mocks={[outdatedMock]} addTypename={false}>
          <GlobalUIRepository enforceVersionCheck={true} />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/version mismatch warning/i)).toBeInTheDocument()
      })
    })

    it('should cache loaded components', async () => {
      const loadComponent = jest.fn()

      const { rerender } = render(
        <MockedProvider mocks={[MOCK_COMPONENT_REGISTRY_QUERY]} addTypename={false}>
          <GlobalUIRepository onComponentLoad={loadComponent} />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(loadComponent).toHaveBeenCalledTimes(3) // Initial load
      })

      // Rerender - should use cache
      rerender(
        <MockedProvider mocks={[MOCK_COMPONENT_REGISTRY_QUERY]} addTypename={false}>
          <GlobalUIRepository onComponentLoad={loadComponent} />
        </MockedProvider>
      )

      // Should not load again
      expect(loadComponent).toHaveBeenCalledTimes(3)
    })

    it('should handle component load failures gracefully', async () => {
      const failingMock = {
        request: MOCK_COMPONENT_REGISTRY_QUERY.request,
        error: new Error('Component load failed'),
      }

      render(
        <MockedProvider mocks={[failingMock]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/failed to load components/i)).toBeInTheDocument()
      })
    })
  })

  describe('Agent-Specific UI Triggering', () => {
    it('should trigger financial UI on financial agent event', async () => {
      const onTrigger = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUITrigger={onTrigger} />
        </MockedProvider>
      )

      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onmessage) {
          ws.onmessage(new MessageEvent('message', {
            data: JSON.stringify({
              type: 'AGENT_EVENT',
              agentType: 'financial',
              action: 'SHOW_DASHBOARD',
              data: { revenue: 150000 }
            })
          }))
        }
      })

      await waitFor(() => {
        expect(onTrigger).toHaveBeenCalledWith(
          'financial-team-ui',
          expect.objectContaining({ revenue: 150000 })
        )
      })
    })

    it('should route events to correct team UI components', async () => {
      const onTrigger = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUITrigger={onTrigger} />
        </MockedProvider>
      )

      // Test different agent types
      const agentTypes = ['financial', 'content', 'analytics', 'sales', 'marketing', 'development']

      for (const agentType of agentTypes) {
        await act(async () => {
          const ws = (global.WebSocket as any).instances?.[0]
          if (ws && ws.onmessage) {
            ws.onmessage(new MessageEvent('message', {
              data: JSON.stringify({
                type: 'AGENT_EVENT',
                agentType,
                action: 'SHOW_UI',
              })
            }))
          }
        })
      }

      await waitFor(() => {
        expect(onTrigger).toHaveBeenCalledTimes(6)
      })
    })

    it('should handle multiple concurrent UI triggers', async () => {
      const onTrigger = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUITrigger={onTrigger} />
        </MockedProvider>
      )

      // Trigger multiple UIs simultaneously
      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onmessage) {
          ['financial', 'content', 'analytics'].forEach(agentType => {
            ws.onmessage(new MessageEvent('message', {
              data: JSON.stringify({
                type: 'AGENT_EVENT',
                agentType,
                action: 'SHOW_UI',
              })
            }))
          })
        }
      })

      await waitFor(() => {
        expect(onTrigger).toHaveBeenCalledTimes(3)
      })
    })
  })

  describe('Error Handling and Resilience', () => {
    it('should recover from GraphQL subscription errors', async () => {
      const errorMock = {
        request: MOCK_UI_EVENTS_SUBSCRIPTION.request,
        error: new Error('Subscription failed'),
      }

      render(
        <MockedProvider mocks={[errorMock, MOCK_UI_EVENTS_SUBSCRIPTION]} addTypename={false}>
          <GlobalUIRepository enableSubscriptions={true} autoReconnect={true} />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/subscription error/i)).toBeInTheDocument()
      })

      // Should attempt to resubscribe
      await waitFor(() => {
        expect(screen.getByText(/reconnecting/i)).toBeInTheDocument()
      }, { timeout: 3000 })
    })

    it('should queue events during connection loss', async () => {
      const onUIEvent = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUIEvent={onUIEvent} enableQueue={true} />
        </MockedProvider>
      )

      // Disconnect
      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onclose) {
          ws.onclose(new CloseEvent('close'))
        }
      })

      // Try to send events while disconnected
      await act(async () => {
        // Events should be queued
      })

      // Reconnect
      await waitFor(() => {
        // Queued events should be processed
        expect(onUIEvent).toHaveBeenCalled()
      }, { timeout: 5000 })
    })

    it('should log errors without crashing', async () => {
      const consoleError = jest.spyOn(console, 'error').mockImplementation()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      // Simulate malformed event
      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onmessage) {
          ws.onmessage(new MessageEvent('message', {
            data: 'invalid json'
          }))
        }
      })

      expect(consoleError).toHaveBeenCalled()
      expect(screen.getByText(/repository initialized/i)).toBeInTheDocument() // Still functional

      consoleError.mockRestore()
    })
  })

  describe('Performance and Optimization', () => {
    it('should handle high-frequency updates efficiently', async () => {
      const onUIEvent = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onUIEvent={onUIEvent} />
        </MockedProvider>
      )

      const startTime = performance.now()

      // Send 1000 events
      await act(async () => {
        for (let i = 0; i < 1000; i++) {
          const ws = (global.WebSocket as any).instances?.[0]
          if (ws && ws.onmessage) {
            ws.onmessage(new MessageEvent('message', {
              data: JSON.stringify({ type: 'UI_UPDATE', count: i })
            }))
          }
        }
      })

      const endTime = performance.now()

      // Should process quickly (< 1 second for 1000 events)
      expect(endTime - startTime).toBeLessThan(1000)
    })

    it('should clean up resources on unmount', async () => {
      const { unmount } = render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository />
        </MockedProvider>
      )

      const ws = (global.WebSocket as any).instances?.[0]
      const closeSpy = jest.spyOn(ws, 'close')

      unmount()

      expect(closeSpy).toHaveBeenCalled()
    })

    it('should use memory efficiently with component caching', async () => {
      render(
        <MockedProvider mocks={[MOCK_COMPONENT_REGISTRY_QUERY]} addTypename={false}>
          <GlobalUIRepository maxCacheSize={10} />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/cache initialized/i)).toBeInTheDocument()
      })

      // Memory usage should stay within limits
      if (performance.memory) {
        expect(performance.memory.usedJSHeapSize).toBeLessThan(100 * 1024 * 1024) // < 100MB
      }
    })
  })

  describe('Security and Validation', () => {
    it('should validate incoming event data', async () => {
      const onInvalidEvent = jest.fn()

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository onInvalidEvent={onInvalidEvent} />
        </MockedProvider>
      )

      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onmessage) {
          ws.onmessage(new MessageEvent('message', {
            data: JSON.stringify({
              type: 'INVALID_TYPE',
              maliciousScript: '<script>alert("xss")</script>'
            })
          }))
        }
      })

      await waitFor(() => {
        expect(onInvalidEvent).toHaveBeenCalled()
      })
    })

    it('should sanitize component data before rendering', async () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository sanitizeData={true} />
        </MockedProvider>
      )

      await act(async () => {
        const ws = (global.WebSocket as any).instances?.[0]
        if (ws && ws.onmessage) {
          ws.onmessage(new MessageEvent('message', {
            data: JSON.stringify({
              type: 'UI_UPDATE',
              component: 'financial-team-ui',
              data: {
                revenue: '<img src=x onerror=alert(1)>150000'
              }
            })
          }))
        }
      })

      await waitFor(() => {
        // Should not contain malicious content
        expect(screen.queryByText(/<img/)).not.toBeInTheDocument()
      })
    })

    it('should require authentication for sensitive components', async () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <GlobalUIRepository requireAuth={true} authToken={null} />
        </MockedProvider>
      )

      await waitFor(() => {
        expect(screen.getByText(/authentication required/i)).toBeInTheDocument()
      })
    })
  })
})
