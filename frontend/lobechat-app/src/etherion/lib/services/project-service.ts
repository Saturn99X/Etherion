import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_PROJECTS_QUERY,
  CREATE_PROJECT_MUTATION,
  UPDATE_PROJECT_MUTATION,
  DELETE_PROJECT_MUTATION,
  GET_CONVERSATIONS_QUERY,
  CREATE_CONVERSATION_MUTATION
} from '@etherion/lib/graphql-operations';

interface ProjectsResponse {
  getProjectsByTenant: Project[];
}

interface CreateProjectResponse {
  createProject: Project;
}

interface UpdateProjectResponse {
  updateProject: Project;
}

interface DeleteProjectResponse {
  deleteProject: boolean;
}

interface ConversationsResponse {
  getConversationsByProject: Conversation[];
}

interface CreateConversationResponse {
  createConversation: Conversation;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  createdAt?: string;
  userId: number;
}

export interface Conversation {
  id: number;
  title: string;
  createdAt?: string;
  projectId: number;
}

export interface CreateProjectInput {
  name: string;
  description: string;
}

export interface CreateConversationInput {
  title: string;
  projectId: number;
}

export class ProjectService {
  static async getProjects(): Promise<Project[]> {
    try {
      const { data } = await getClient().query<ProjectsResponse>({
        query: GET_PROJECTS_QUERY,
        fetchPolicy: 'network-only',
      });

      return data?.getProjectsByTenant || [];
    } catch (error) {
      console.error('Get projects error:', error);
      throw error;
    }
  }

  static async createProject(projectInput: CreateProjectInput): Promise<Project> {
    try {
      const { data } = await getClient().mutate<CreateProjectResponse>({
        mutation: CREATE_PROJECT_MUTATION,
        variables: { project_input: projectInput },
      });

      if (!data?.createProject) {
        throw new Error('Create project failed - no response data');
      }

      return data.createProject;
    } catch (error) {
      console.error('Create project error:', error);
      throw error;
    }
  }

  static async updateProject(projectId: number, projectInput: CreateProjectInput): Promise<Project> {
    try {
      const { data } = await getClient().mutate<UpdateProjectResponse>({
        mutation: UPDATE_PROJECT_MUTATION,
        variables: {
          project_id: projectId,
          project_input: projectInput,
        },
      });

      if (!data?.updateProject) {
        throw new Error('Update project failed - no response data');
      }

      return data.updateProject;
    } catch (error) {
      console.error('Update project error:', error);
      throw error;
    }
  }

  static async deleteProject(projectId: number): Promise<boolean> {
    try {
      const { data } = await getClient().mutate<DeleteProjectResponse>({
        mutation: DELETE_PROJECT_MUTATION,
        variables: { project_id: projectId },
      });

      return data?.deleteProject === true;
    } catch (error) {
      console.error('Delete project error:', error);
      throw error;
    }
  }

  static async getConversations(projectId: number): Promise<Conversation[]> {
    try {
      const { data } = await getClient().query<ConversationsResponse>({
        query: GET_CONVERSATIONS_QUERY,
        variables: { project_id: projectId },
        fetchPolicy: 'network-only',
      });

      return data?.getConversationsByProject || [];
    } catch (error) {
      console.error('Get conversations error:', error);
      throw error;
    }
  }

  static async createConversation(conversationInput: CreateConversationInput): Promise<Conversation> {
    try {
      const { data } = await getClient().mutate<CreateConversationResponse>({
        mutation: CREATE_CONVERSATION_MUTATION,
        variables: { conversation_input: conversationInput },
      });

      if (!data?.createConversation) {
        throw new Error('Create conversation failed - no response data');
      }

      return data.createConversation;
    } catch (error) {
      console.error('Create conversation error:', error);
      throw error;
    }
  }
}
