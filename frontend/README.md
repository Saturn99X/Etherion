# Etherion Frontend

A Next.js frontend application for the Etherion platform with real-time goal execution and project management.

## Features

- **Real-time Goal Execution**: Submit goals and track execution progress in real-time
- **Google OAuth Authentication**: Secure authentication using Google OAuth 2.0
- **Project Management**: Create and manage projects to organize your work
- **Beautiful UI**: Glassmorphism design with dark/light theme support
- **GraphQL Integration**: Full GraphQL client with real-time subscriptions

## Setup

### 1. Environment Configuration

Create a `.env.local` file in the frontend directory:

```env
# Google OAuth Configuration
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_client_id_here

# GraphQL Endpoint
NEXT_PUBLIC_GRAPHQL_ENDPOINT=http://localhost:8080/graphql

# Environment
NEXT_PUBLIC_ENVIRONMENT=development
```

### 2. Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client IDs"
5. Set application type to "Web application"
6. Add authorized redirect URIs:
   - Development: `http://localhost:3000/auth/callback`
   - Production: `https://yourdomain.com/auth/callback`
7. Copy the Client ID and add it to your `.env.local` file

### 3. Backend Setup

Make sure the backend is running on `http://localhost:8080` with the following environment variables:

```env
# Google OAuth (backend)
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/etherionai

# Redis
REDIS_URL=redis://localhost:6379

# JWT Secret
JWT_SECRET_KEY=your_jwt_secret_key_here
```

### 4. Start the Development Server

```bash
npm run dev
# or
pnpm dev
```

The application will be available at `http://localhost:3000`.

## Usage

1. **Authentication**: Click "Sign in with Google" to authenticate
2. **Project Selection**: Use the project selector in the sidebar to choose or create projects
3. **Goal Execution**: Enter your goals in the input bar and click "Execute Goal"
4. **Real-time Tracking**: Watch your goals execute in real-time with live progress updates
5. **Project Management**: Create and manage projects to organize your work

## Architecture

### Key Components

- **Apollo Client**: GraphQL client with authentication and error handling
- **Auth Store**: Zustand store for authentication state management
- **Job Store**: State management for tracking goal execution jobs
- **Real-time Subscriptions**: GraphQL subscriptions for live updates
- **Project Management**: Full CRUD operations for projects and conversations

### Authentication Flow

1. User clicks "Sign in with Google"
2. Redirected to Google OAuth
3. Google redirects back with authorization code
4. Frontend exchanges code for JWT token via GraphQL mutation
5. Token stored in localStorage and Apollo Client
6. User authenticated and can access protected features

### Goal Execution Flow

1. User submits goal via GoalInputBar component
2. Frontend calls `executeGoal` GraphQL mutation
3. Backend creates job and returns job ID
4. Frontend subscribes to job status updates
5. Real-time progress displayed to user
6. Final results shown when job completes

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run linting

### Code Structure

```
frontend/
├── app/                    # Next.js app router pages
├── components/            # React components
│   ├── auth/             # Authentication components
│   ├── ui/               # Reusable UI components
│   └── ...               # Feature-specific components
├── lib/                  # Utilities and configurations
│   ├── services/         # API service classes
│   ├── stores/           # Zustand stores
│   ├── apollo-client.ts  # GraphQL client setup
│   └── ...
├── hooks/                # Custom React hooks
└── styles/               # Global styles
```

## Production Deployment

1. Set up environment variables for production
2. Configure Google OAuth for production domain
3. Build the application: `npm run build`
4. Deploy to your hosting platform

## Troubleshooting

### Common Issues

1. **OAuth Redirect Issues**: Make sure redirect URIs are correctly configured in Google Cloud Console
2. **GraphQL Errors**: Check that backend is running on correct port
3. **Authentication Issues**: Clear localStorage and try logging in again
4. **Real-time Updates Not Working**: Ensure Redis is running and configured

### Debug Mode

Enable debug logging by setting `NEXT_PUBLIC_ENVIRONMENT=development` in your environment variables.
