import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { MessageBubble } from '@/components/message-bubble'

const baseMessage = {
  id: 'm1',
  role: 'assistant' as const,
  content: 'Hello world',
  timestamp: new Date(),
  metadata: { cot: 'reasoning', artifacts: [{ kind: 'doc', content: 'doc' }] },
}

describe('MessageBubble actions and toggles', () => {
  it('renders action buttons and triggers handlers', () => {
    const onBranch = jest.fn()
    const onToggleCot = jest.fn()
    const onToggleArtifacts = jest.fn()

    const { container } = render(
      <MessageBubble
        message={baseMessage}
        onBranch={onBranch}
        onToggleCot={onToggleCot}
        onToggleArtifacts={onToggleArtifacts}
        statusChip="Running"
        forkIndicator
      />
    )

    // reveal hover actions
    fireEvent.mouseEnter(screen.getByText(/Hello world/).closest('div') as Element)

    fireEvent.click(screen.getByText(/Branch/i))
    expect(onBranch).toHaveBeenCalled()

    fireEvent.click(screen.getByText(/Reasoning/i))
    expect(onToggleCot).toHaveBeenCalled()

    fireEvent.click(screen.getByText(/Artifacts/i))
    expect(onToggleArtifacts).toHaveBeenCalled()

    // shows status chip
    expect(screen.getByText(/Running/)).toBeInTheDocument()
    // shows fork indicator label
    expect(screen.getByText(/Branch start/)).toBeInTheDocument()
  })
})
