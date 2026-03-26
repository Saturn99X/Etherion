import { gql } from '@apollo/client';

export const GET_AGENTS = gql`
  query GetAgents {
    agents {
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
