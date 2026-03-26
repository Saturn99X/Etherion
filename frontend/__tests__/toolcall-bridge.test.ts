import { redactParams, summarizeParams, stubSuggestionsFromGoal } from '@/lib/lobe/toolcall-bridge'

describe('toolcall-bridge helpers', () => {
  test('redactParams hides secret-ish keys recursively', () => {
    const input = { a: 1, apiKey: 'secret', nested: { token: 't', keep: 'x' } }
    const out = redactParams(input)
    expect(out.a).toBe(1)
    expect(out.apiKey).toBe('***')
    expect(out.nested.token).toBe('***')
    expect(out.nested.keep).toBe('x')
  })

  test('summarizeParams shows up to three keys', () => {
    const s1 = summarizeParams({})
    expect(s1).toMatch(/No params/i)
    const s2 = summarizeParams({ a: 1, b: 2, c: 3, d: 4 })
    expect(s2).toMatch(/a:/)
    expect(s2).toMatch(/b:/)
    expect(s2).toMatch(/c:/)
  })

  test('stubSuggestionsFromGoal returns a web_search suggestion', () => {
    const res = stubSuggestionsFromGoal('find latest news on AI', 'm1')
    expect(res.length).toBe(1)
    expect(res[0].toolName).toBe('web_search')
    expect(res[0].messageId).toBe('m1')
    expect(res[0].previewParams.query).toMatch(/latest news/i)
  })
})
