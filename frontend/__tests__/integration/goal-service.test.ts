import { GoalService } from '@/lib/services/goal-service'

jest.mock('@/lib/apollo-client', () => ({
  getClient: () => ({
    mutate: jest.fn().mockResolvedValue({ data: { executeGoal: { success: true, job_id: 'job-x', status: 'QUEUED', message: 'ok' } } }),
    query: jest.fn(),
  }),
}))

jest.mock('@/lib/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ user: { user_id: 'u-1' } }),
  },
}))

jest.mock('@/lib/graphql-operations', () => ({
  EXECUTE_GOAL_MUTATION: {} as any,
  GET_ARCHIVED_TRACE_SUMMARY: {} as any,
  CANCEL_JOB_MUTATION: {} as any,
}))

describe('GoalService', () => {
  it('executeGoal passes plan_mode and search_force and userId', async () => {
    const { getClient } = require('@/lib/apollo-client')
    const client = getClient()
    const spy = jest.spyOn(client, 'mutate')

    await GoalService.executeGoal({ goal: 'hello', plan_mode: true, search_force: false })

    expect(spy).toHaveBeenCalled()
    const vars = spy.mock.calls[0][0].variables.goalInput
    expect(vars.userId).toBe('u-1')
    expect(vars.plan_mode).toBe(true)
    expect(vars.search_force).toBe(false)
  })

  it('cancelJob sends mutation with job_id', async () => {
    const { getClient } = require('@/lib/apollo-client')
    const client = getClient()
    const spy = jest.spyOn(client, 'mutate')

    await GoalService.cancelJob('job-abc')

    expect(spy).toHaveBeenCalled()
    const vars = spy.mock.calls[0][0].variables
    expect(vars.job_id).toBe('job-abc')
  })
})
