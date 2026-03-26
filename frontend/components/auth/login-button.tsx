"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getGoogleOAuthUrl, getGithubOAuthUrl } from '@/lib/services/auth-service';
import { useToast } from '@/hooks/use-toast';

interface LoginButtonProps {
  provider?: 'google' | 'github';
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
  className?: string;
  children?: React.ReactNode;
}

export function LoginButton({
  provider = 'google',
  variant = 'default',
  size = 'default',
  className = '',
  children
}: LoginButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const { isAuthenticated } = useAuthStore();
  const { toast } = useToast();

  const handleLogin = async () => {
    if (isAuthenticated) return;

    setIsLoading(true);
    try {
      // Pre-validate environment - will throw clear error if not configured
      let oauthUrl = '';

      // Save provider to decide which backend mutation to call on callback
      try { window.localStorage.setItem('oauth_provider', provider); } catch (_) { }

      // Generate OAuth URL (this will validate client ID exists)
      try {
        if (provider === 'google') oauthUrl = getGoogleOAuthUrl();
        else if (provider === 'github') oauthUrl = getGithubOAuthUrl();
      } catch (error) {
        // Enhance error message if it's a configuration issue
        const errorMsg = error instanceof Error ? error.message : 'OAuth URL could not be generated';
        if (errorMsg.includes('not configured')) {
          throw new Error(`${provider.charAt(0).toUpperCase() + provider.slice(1)} login is not configured. Please contact support.`);
        }
        throw error;
      }

      if (!oauthUrl) throw new Error('OAuth URL could not be generated');

      // Track OAuth initiation for debugging hung states
      try {
        window.localStorage.setItem('oauth_initiated_at', Date.now().toString());
        window.localStorage.setItem('oauth_initiated_provider', provider);
      } catch (_) { }

      window.location.href = oauthUrl;
    } catch (error) {
      console.error('Login error:', error);
      toast({
        title: 'Authentication Error',
        description: error instanceof Error ? error.message : 'Unable to start OAuth flow. Please refresh and try again.',
        variant: 'destructive',
      });
      setIsLoading(false);
    }
  };

  if (isAuthenticated) {
    return null; // Don't show login button if already authenticated
  }

  return (
    <Button
      onClick={handleLogin}
      disabled={isLoading}
      variant={variant}
      size={size}
      className={`gap-2 ${className}`}
    >
      {isLoading ? (
        <>
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          Connecting...
        </>
      ) : (
        children || (
          <>
            {provider === 'google' && (
              <svg className="h-4 w-4" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
            )}
            {provider === 'github' && (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M12 .5a12 12 0 00-3.79 23.4c.6.11.82-.26.82-.58v-2.02c-3.34.73-4.04-1.61-4.04-1.61-.55-1.38-1.35-1.74-1.35-1.74-1.1-.75.08-.74.08-.74 1.22.09 1.86 1.26 1.86 1.26 1.08 1.86 2.84 1.32 3.53 1.01.11-.78.42-1.32.76-1.63-2.66-.3-5.47-1.33-5.47-5.95 0-1.31.47-2.38 1.25-3.22-.13-.3-.54-1.52.12-3.17 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 016 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.65.25 2.87.12 3.17.78.84 1.25 1.91 1.25 3.22 0 4.63-2.81 5.65-5.49 5.95.43.37.82 1.1.82 2.22v3.29c0 .32.22.69.83.58A12 12 0 0012 .5z" clipRule="evenodd" />
              </svg>
            )}
            {provider === 'google' && 'Sign in with Google'}
            {provider === 'github' && 'Sign in with GitHub'}
          </>
        )
      )}
    </Button>
  );
}
