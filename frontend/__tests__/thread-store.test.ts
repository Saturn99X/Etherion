import { useThreadStore } from '@/lib/stores/useThreadStore'

describe('useThreadStore (Step 2 selectors/actions)', () => {
  const threadId = 't-1'

  beforeEach(() => {
    // reset store between tests
    const { threads } = useThreadStore.getState()
    for (const key of Object.keys(threads)) delete threads[key]
    useThreadStore.setState({ threads: {} })
  })

  it('adds messages and gets messages by branch', () => {
    const { addMessage, getMessagesByBranch, createBranch } = useThreadStore.getState()

    addMessage(threadId, {
      id: 'm1', role: 'assistant', content: 'Hello', timestamp: new Date().toISOString(),
    })
    addMessage(threadId, {
      id: 'm2', role: 'user', content: 'World', timestamp: new Date().toISOString(),
    })

    const bid = createBranch(threadId, 'm1')
    expect(typeof bid).toBe('string')
    expect(bid.length).toBeGreaterThan(0)

    const all = getMessagesByBranch(threadId)
    expect(all.length).toBeGreaterThan(0)

    const onlyBranch = getMessagesByBranch(threadId, bid)
    // at least fork message should be in branch slice
    expect(onlyBranch.some((m) => m.id === 'm1')).toBeTruthy()
  })

  it('toggles CoT and Artifacts flags', () => {
    const { addMessage, toggleCot, toggleArtifacts } = useThreadStore.getState()
    addMessage(threadId, { id: 'x', role: 'assistant', content: 'a', timestamp: new Date().toISOString(), metadata: {} })

    toggleCot(threadId, 'x')
    let msg = useThreadStore.getState().threads[threadId].find((m) => m.id === 'x')
    expect(msg?.metadata?.showCot).toBe(true)

    toggleArtifacts(threadId, 'x')
    msg = useThreadStore.getState().threads[threadId].find((m) => m.id === 'x')
    expect(msg?.metadata?.showArtifacts).toBe(true)
  })

  it('updates message content and metadata', () => {
    const { addMessage, updateMessageContent, setMessageMetadata } = useThreadStore.getState()
    addMessage(threadId, { id: 'y', role: 'assistant', content: '', timestamp: new Date().toISOString(), metadata: {} })

    updateMessageContent(threadId, 'y', 'streamed')
    let msg = useThreadStore.getState().threads[threadId].find((m) => m.id === 'y')
    expect(msg?.content).toBe('streamed')

    setMessageMetadata(threadId, 'y', { cot: 'reason', showCot: true })
    msg = useThreadStore.getState().threads[threadId].find((m) => m.id === 'y')
    expect(msg?.metadata?.cot).toBe('reason')
    expect(msg?.metadata?.showCot).toBe(true)
  })
})
