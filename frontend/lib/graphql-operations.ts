import { gql } from '@apollo/client';

// ============================================================================
// AUTHENTICATION OPERATIONS
// ============================================================================

export const GOOGLE_LOGIN_MUTATION = gql`
  mutation GoogleLogin($code: String!, $invite_token: String, $redirect_uri: String) {
    googleLogin(code: $code, invite_token: $invite_token, redirect_uri: $redirect_uri) {
      access_token
      token_type
      user {
        user_id
        email
        name
        provider
        profile_picture_url
        tenant_subdomain
      }
    }
  }`;

// ============================================================================
// AGENT TEAM OPERATIONS
// ============================================================================

export const LIST_AGENT_TEAMS_QUERY = gql`
  query ListAgentTeams($limit: Int, $offset: Int) {
    listAgentTeams(limit: $limit, offset: $offset) {
      id
      name
      description
      createdAt
      lastUpdatedAt
      isActive
      isSystemTeam
      version
      customAgentIDs
      preApprovedToolNames
    }
  }
`;

// =========================================================================
// AGENT BLUEPRINT CREATION (stubs; align with backend schema when available)
// =========================================================================

export const CREATE_CUSTOM_AGENT_DEFINITION = gql`
  mutation CreateCustomAgentDefinition($input: CustomAgentDefinitionInput!) {
    createCustomAgentDefinition(input: $input) {
      id
      name
      version
    }
  }
`;

export const CREATE_AGENT_TEAM_FROM_DEFINITION = gql`
  mutation CreateAgentTeam($team_input: AgentTeamInput!) {
    createAgentTeam(team_input: $team_input) {
      id
      name
      preApprovedToolNames
      version
    }
  }
`;

export const CREATE_AGENT_TEAM_MUTATION = gql`
  mutation CreateAgentTeam($team_input: AgentTeamInput!) {
    createAgentTeam(team_input: $team_input) {
      id
      name
      description
      createdAt
      lastUpdatedAt
      isActive
      isSystemTeam
      version
      customAgentIDs
      preApprovedToolNames
    }
  }
`;

export const UPDATE_AGENT_TEAM_MUTATION = gql`
  mutation UpdateAgentTeam($agent_team_id: String!, $name: String, $description: String, $pre_approved_tool_names: [String!]) {
    updateAgentTeam(agent_team_id: $agent_team_id, name: $name, description: $description, pre_approved_tool_names: $pre_approved_tool_names)
  }
`;

export const GITHUB_LOGIN_MUTATION = gql`
  mutation GithubLogin($code: String!, $invite_token: String, $redirect_uri: String) {
    githubLogin(code: $code, invite_token: $invite_token, redirect_uri: $redirect_uri) {
      access_token
      token_type
      user {
        user_id
        email
        name
        provider
        profile_picture_url
        tenant_subdomain
      }
    }
  }
`;

export const MICROSOFT_LOGIN_MUTATION = gql`
  mutation MicrosoftLogin($code: String!, $invite_token: String, $redirect_uri: String) {
    microsoftLogin(code: $code, invite_token: $invite_token, redirect_uri: $redirect_uri) {
      access_token
      token_type
      user {
        user_id
        email
        name
        provider
        profile_picture_url
        tenant_subdomain
      }
    }
  }
`;

export const PASSWORD_SIGNUP_MUTATION = gql`
  mutation PasswordSignup(
    $email: String!
    $password: String!
    $name: String
    $invite_token: String
    $subdomain: String
  ) {
    passwordSignup(
      email: $email
      password: $password
      name: $name
      invite_token: $invite_token
      subdomain: $subdomain
    ) {
      access_token
      token_type
      user {
        user_id
        email
        name
        provider
        profile_picture_url
        tenant_subdomain
      }
    }
  }
`;

export const PASSWORD_LOGIN_MUTATION = gql`
  mutation PasswordLogin($email: String!, $password: String!, $invite_token: String) {
    passwordLogin(email: $email, password: $password, invite_token: $invite_token) {
      access_token
      token_type
      user {
        user_id
        email
        name
        provider
        profile_picture_url
        tenant_subdomain
      }
    }
  }
`;

export const GET_CURRENT_USER_QUERY = gql`
  query GetCurrentUser {
    getCurrentUser {
      user_id
      created_at
    }
  }
`;

export const LOGOUT_MUTATION = gql`
  mutation Logout($token: String!) {
    logout(token: $token)
  }
`;
// ============================================================================
// GOAL EXECUTION OPERATIONS
// ============================================================================

export const EXECUTE_GOAL_MUTATION = gql`
  mutation ExecuteGoal($goalInput: GoalInput!) {
    executeGoal(goalInput: $goalInput) {
      success
      job_id
      status
      message
    }
  }
`;

// ============================================================================
// JOB TRACKING OPERATIONS
// ============================================================================
export const SUBSCRIBE_TO_JOB_STATUS = gql`
  subscription SubscribeToJobStatus($job_id: String!) {
    subscribeToJobStatus(job_id: $job_id) {
      job_id
      status
      timestamp
      message
      progress_percentage
      current_step_description
      error_message
      additional_data
    }
  }
`;

export const SUBSCRIBE_TO_EXECUTION_TRACE = gql`
  subscription SubscribeToExecutionTrace($job_id: String!) {
    subscribeToExecutionTrace(job_id: $job_id) {
      job_id
      status
      timestamp
      current_step_description
      additional_data
    }
  }
`;

export const SUBSCRIBE_TO_UI_EVENTS = gql`
  subscription SubscribeToUIEvents($tenant_id: Int!) {
    subscribeToUIEvents(tenant_id: $tenant_id) {
      job_id
      status
      timestamp
      message
      additional_data
    }
  }
`;

export const GET_ARCHIVED_TRACE_SUMMARY = gql`
  query GetArchivedTraceSummary($job_id: String!) {
    getArchivedTraceSummary(job_id: $job_id)
  }
`;

// ============================================================================
// FEEDBACK OPERATIONS
// ============================================================================

export const SUBMIT_FEEDBACK_MUTATION = gql`
  mutation SubmitFeedback($feedback_input: FeedbackInput!) {
    submitFeedback(feedback_input: $feedback_input)
  }
`;

// ============================================================================
// PROJECT MANAGEMENT OPERATIONS
// ============================================================================

export const GET_PROJECTS_QUERY = gql`
  query GetProjectsByTenant {
    getProjectsByTenant {
      id
      name
      description
      createdAt
      userId
    }
  }
`;

export const CREATE_PROJECT_MUTATION = gql`
  mutation CreateProject($project_input: ProjectInput!) {
    createProject(project_input: $project_input) {
      id
      name
      description
      createdAt
      userId
    }
  }
`;

export const UPDATE_PROJECT_MUTATION = gql`
  mutation UpdateProject($project_id: Int!, $project_input: ProjectInput!) {
    updateProject(project_id: $project_id, project_input: $project_input) {
      id
      name
      description
      createdAt
      userId
    }
  }
`;

export const DELETE_PROJECT_MUTATION = gql`
  mutation DeleteProject($project_id: Int!) {
    deleteProject(project_id: $project_id)
  }
`;

// ============================================================================
// CONVERSATION OPERATIONS
// ============================================================================

export const GET_CONVERSATIONS_QUERY = gql`
  query GetConversationsByProject($project_id: Int!) {
    getConversationsByProject(project_id: $project_id) {
      id
      title
      createdAt
      projectId
    }
  }
`;

export const CREATE_CONVERSATION_MUTATION = gql`
  mutation CreateConversation($conversation_input: ConversationInput!) {
    createConversation(conversation_input: $conversation_input) {
      id
      title
      createdAt
      projectId
    }
  }
`;

// ============================================================================
// HEALTH CHECK
// ============================================================================

export const HEALTH_CHECK_QUERY = gql`
  query HealthCheck {
    health_check
  }
`;

// ============================================================================
// TENANT OPERATIONS
// ============================================================================

export const CREATE_TENANT_MUTATION = gql`
  mutation CreateTenant($tenant_input: TenantInput!) {
    createTenant(tenant_input: $tenant_input) {
      id
      tenantId
      subdomain
      name
      adminEmail
      createdAt
      inviteToken
    }
  }
`;

// =============================================================================
// REPOSITORY OPERATIONS
// =============================================================================

export const LIST_REPOSITORY_ASSETS = gql`
  query ListRepositoryAssets($limit: Int, $jobId: String, $include_download: Boolean) {
    listRepositoryAssets(limit: $limit, jobId: $jobId, include_download: $include_download) {
      assetId
      jobId
      filename
      mimeType
      sizeBytes
      gcsUri
      createdAt
      downloadUrl
      previewBase64
    }
  }
`;

// ============================================================================
// FRAGMENT DEFINITIONS
// ============================================================================
export const USER_AUTH_FRAGMENT = gql`
  fragment UserAuth on UserAuthType {
    user_id
    email
    name
    provider
    profile_picture_url
  }
`;

export const JOB_RESPONSE_FRAGMENT = gql`
  fragment JobResponse on JobResponse {
    success
    job_id
    status
    message
  }
`;

export const JOB_STATUS_UPDATE_FRAGMENT = gql`
  fragment JobStatusUpdate on JobStatusUpdate {
    job_id
    status
    timestamp
    message
    progress_percentage
    current_step_description
    error_message
    additional_data
  }
`;

export const PROJECT_FRAGMENT = gql`
  fragment Project on ProjectType {
    id
    name
    description
    createdAt
    userId
  }
`;

// ============================================================================
// AGENT MANAGEMENT OPERATIONS
// ============================================================================

export const GET_AGENTS_QUERY = gql`
  query GetAgents($tenant_id: Int!) {
    getAgents(tenant_id: $tenant_id) {
      id
      name
      description
      createdAt
      lastUsed
      status
      agentType
      capabilities
      performanceMetrics
    }
  }
`;

export const CREATE_AGENT_MUTATION = gql`
  mutation CreateAgent($agent_input: AgentInput!) {
    createAgent(agent_input: $agent_input) {
      id
      name
      description
      status
    }
  }
`;

export const UPDATE_AGENT_MUTATION = gql`
  mutation UpdateAgent($agent_id: String!, $agent_input: AgentInput!) {
    updateAgent(agent_id: $agent_id, agent_input: $agent_input) {
      id
      name
      description
      status
    }
  }
`;

export const DELETE_AGENT_MUTATION = gql`
  mutation DeleteAgent($agent_id: String!) {
    deleteAgent(agent_id: $agent_id)
  }
`;

export const EXECUTE_AGENT_MUTATION = gql`
  mutation ExecuteAgent($agent_id: String!, $input: String!) {
    executeAgent(agent_id: $agent_id, input: $input) {
      success
      result
      executionTime
      cost
    }
  }
`;

// ============================================================================
// INTEGRATION MANAGEMENT OPERATIONS
// ============================================================================

export const GET_INTEGRATIONS_QUERY = gql`
  query GetIntegrations($tenant_id: Int!) {
    getIntegrations(tenant_id: $tenant_id) {
      serviceName
      status
      lastConnected
      errorMessage
      capabilities
    }
  }
`;

export const CONNECT_INTEGRATION_MUTATION = gql`
  mutation ConnectIntegration($service_name: String!, $credentials: String!) {
    connectIntegration(service_name: $service_name, credentials: $credentials) {
      serviceName
      status
      validationErrors
    }
  }
`;

export const TEST_INTEGRATION_MUTATION = gql`
  mutation TestIntegration($service_name: String!) {
    testIntegration(service_name: $service_name) {
      success
      testResult
      errorMessage
    }
  }
`;

export const DISCONNECT_INTEGRATION_MUTATION = gql`
  mutation DisconnectIntegration($service_name: String!) {
    disconnectIntegration(service_name: $service_name)
  }
`;

// ============================================================================
// MCP TOOL OPERATIONS
// ============================================================================

export const GET_AVAILABLE_MCP_TOOLS_QUERY = gql`
  query GetAvailableMCPTools {
    getAvailableMCPTools {
      name
      description
      category
      requiredCredentials
      capabilities
      status
    }
  }
`;

export const EXECUTE_MCP_TOOL_MUTATION = gql`
  mutation ExecuteMCPTool($tool_name: String!, $params: String!) {
    executeMCPTool(tool_name: $tool_name, params: $params) {
      success
      result
      executionTime
      errorMessage
      toolOutput
    }
  }
`;

export const MANAGE_MCP_CREDENTIALS_MUTATION = gql`
  mutation ManageMCPCredentials($tool_name: String!, $credentials: String!) {
    manageMCPCredentials(tool_name: $tool_name, credentials: $credentials) {
      success
      validationErrors
    }
  }
`;

export const TEST_MCP_TOOL_MUTATION = gql`
  mutation TestMCPTool($tool_name: String!) {
    testMCPTool(tool_name: $tool_name) {
      success
      testResult
      errorMessage
    }
  }
`;

// ============================================================================
// TONE PROFILE OPERATIONS
// ============================================================================

export const GET_TONE_PROFILES_QUERY = gql`
  query GetToneProfiles($user_id: Int!) {
    getToneProfiles(user_id: $user_id) {
      id
      name
      type
      description
      usageCount
      lastUsed
      effectiveness
    }
  }
`;

export const CREATE_TONE_PROFILE_MUTATION = gql`
  mutation CreateToneProfile($profile_input: ToneProfileInput!) {
    createToneProfile(profile_input: $profile_input) {
      id
      name
      type
      description
    }
  }
`;

export const UPDATE_TONE_PROFILE_MUTATION = gql`
  mutation UpdateToneProfile($profile_id: String!, $profile_input: ToneProfileInput!) {
    updateToneProfile(profile_id: $profile_id, profile_input: $profile_input) {
      id
      name
      type
      description
    }
  }
`;

export const DELETE_TONE_PROFILE_MUTATION = gql`
  mutation DeleteToneProfile($profile_id: String!) {
    deleteToneProfile(profile_id: $profile_id)
  }
`;

export const APPLY_TONE_PROFILE_MUTATION = gql`
  mutation ApplyToneProfile($profile_id: String!, $goal_id: String!) {
    applyToneProfile(profile_id: $profile_id, goal_id: $goal_id)
  }
`;

// ============================================================================
// JOB HISTORY OPERATIONS
// ============================================================================

export const GET_JOB_HISTORY_QUERY = gql`
  query GetJobHistory($limit: Int, $offset: Int, $status: String, $date_from: String, $date_to: String) {
    getJobHistory(limit: $limit, offset: $offset, status: $status, date_from: $date_from, date_to: $date_to) {
      jobs {
        id
        goal
        status
        createdAt
        completedAt
        duration
        totalCost
        modelUsed
        tokenCount
        successRate
      }
      totalCount
      pageInfo {
        hasNextPage
        hasPreviousPage
      }
    }
  }
`;

export const GET_JOB_DETAILS_QUERY = gql`
  query GetJobDetails($job_id: String!) {
    getJobDetails(job_id: $job_id) {
      id
      goal
      status
      createdAt
      completedAt
      executionTrace {
        steps {
          stepNumber
          timestamp
          stepType
          thought
          actionTool
          actionInput
          observationResult
          stepCost
          modelUsed
        }
      }
      performanceMetrics
      errorLogs
    }
  }
`;

// ============================================================================
// JOB CONTROL OPERATIONS
// ============================================================================

export const CANCEL_JOB_MUTATION = gql`
  mutation CancelJob($job_id: String!) {
    cancelJob(job_id: $job_id)
  }
`;

// ============================================================================
// AUTHENTICATION OPERATIONS
// ============================================================================
export const AUTH_RESPONSE_FRAGMENT = gql`
  fragment AuthResponseUser on User {
    id
    username
    email
    tenant_subdomain
  }
`;

export const SIGNUP_MUTATION = gql`
  mutation Signup($username: String!, $email: String!, $password: String!, $tenant_subdomain: String!) {
    signup(username: $username, email: $email, password: $password, tenant_subdomain: $tenant_subdomain) {
      user {
        ...AuthResponseUser
      }
      token
    }
  }
  ${AUTH_RESPONSE_FRAGMENT}
`;

export const SIGNIN_MUTATION = gql`
  mutation Signin($username: String!, $password: String!, $tenant_subdomain: String!) {
    signin(username: $username, password: $password, tenant_subdomain: $tenant_subdomain) {
      user {
        ...AuthResponseUser
      }
      token
    }
  }
  ${AUTH_RESPONSE_FRAGMENT}
`;

// ============================================================================
// USER SETTINGS
// =========================================================================

export const GET_USER_SETTINGS_QUERY = gql`
  query GetUserSettings {
    getUserSettings
  }
`;

export const UPDATE_USER_SETTINGS_MUTATION = gql`
  mutation UpdateUserSettings($settings: JSON!) {
    updateUserSettings(settings: $settings)
  }
`;

// =========================================================================
// THREADS AND MESSAGES
// =========================================================================

export const GET_THREAD_QUERY = gql`
  query GetThread($thread_id: String!) {
    getThread(thread_id: $thread_id) {
      threadId
      title
      teamId
      createdAt
      lastActivityAt
    }
  }
`;

export const LIST_THREADS_QUERY = gql`
  query ListThreads($limit: Int, $offset: Int) {
    listThreads(limit: $limit, offset: $offset) {
      threadId
      title
      teamId
      createdAt
      lastActivityAt
    }
  }
`;

export const LIST_MESSAGES_QUERY = gql`
  query ListMessages($thread_id: String!, $branch_id: String, $limit: Int, $offset: Int) {
    listMessages(thread_id: $thread_id, branch_id: $branch_id, limit: $limit, offset: $offset) {
      messageId
      threadId
      role
      content
      parentId
      branchId
      createdAt
    }
  }
`;
