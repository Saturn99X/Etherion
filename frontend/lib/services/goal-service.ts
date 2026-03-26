import { getClient } from '@/lib/apollo-client';
import { useAuthStore } from '@/lib/stores/auth-store';
import {
  EXECUTE_GOAL_MUTATION,
  GET_ARCHIVED_TRACE_SUMMARY,
  CANCEL_JOB_MUTATION,
} from '@/lib/graphql-operations';

interface ExecuteGoalResponse {
  executeGoal: {
    success: boolean;
    job_id: string;
    status: string;
    message: string;
  };
}

interface ArchivedTraceResponse {
  getArchivedTraceSummary: string | null;
}

export interface GoalInput {
  goal: string;
  context?: string;
  output_format_instructions?: string;
  agentTeamId?: string;
  plan_mode?: boolean;
  search_force?: boolean;
}

export interface JobResponse {
  success: boolean;
  job_id: string;
  status: string;
  message: string;
}

export class GoalService {
  static async executeGoal(goalInput: GoalInput): Promise<JobResponse> {
    const { user } = useAuthStore.getState();

    if (!user) {
      throw new Error('User must be authenticated to execute goals');
    }

    try {
      const { data } = await getClient().mutate<ExecuteGoalResponse>({
        mutation: EXECUTE_GOAL_MUTATION,
        variables: {
          goalInput: {
            ...goalInput,
            userId: user.user_id,
            plan_mode: goalInput.plan_mode,
            search_force: goalInput.search_force,
          },
        },
      });

      if (!data?.executeGoal) {
        throw new Error('Goal execution failed - no response data');
      }

      return data.executeGoal;
    } catch (error) {
      console.error('Goal execution error:', error);
      throw error;
    }
  }

  static async getArchivedTraceSummary(jobId: string): Promise<string | null> {
    try {
      const { data } = await getClient().query<ArchivedTraceResponse>({
        query: GET_ARCHIVED_TRACE_SUMMARY,
        variables: { job_id: jobId },
        fetchPolicy: 'network-only',
      });

      return data?.getArchivedTraceSummary || null;
    } catch (error) {
      console.error('Get archived trace summary error:', error);
      return null;
    }
  }

  static async cancelJob(jobId: string): Promise<boolean> {
    try {
      const { data } = await getClient().mutate({
        mutation: CANCEL_JOB_MUTATION,
        variables: { job_id: jobId },
      });
      return Boolean((data as any)?.cancelJob);
    } catch (error) {
      console.error('Cancel job error:', error);
      return false;
    }
  }
}
