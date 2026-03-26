"use client";

import { useState } from 'react';
import { Button, message } from 'antd';
import { useAuthStore } from '@etherion/stores/auth-store';
import { getGoogleOAuthUrl, getGithubOAuthUrl } from '@etherion/lib/services/auth-service';
import { Icon } from '@lobehub/ui';
import { GoogleOutlined, GithubOutlined } from '@ant-design/icons';
import { Loader2 } from 'lucide-react';

interface LoginButtonProps {
    provider?: 'google' | 'github';
    block?: boolean;
    type?: 'primary' | 'default' | 'text' | 'link';
    size?: 'small' | 'middle' | 'large';
    className?: string;
    children?: React.ReactNode;
}

export function LoginButton({
    provider = 'google',
    block = false,
    type = 'default',
    size = 'middle',
    className = '',
    children
}: LoginButtonProps) {
    const [isLoading, setIsLoading] = useState(false);
    const { isAuthenticated } = useAuthStore();

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
            message.error(error instanceof Error ? error.message : 'Unable to start OAuth flow. Please refresh and try again.');
            setIsLoading(false);
        }
    };

    if (isAuthenticated) {
        return null; // Don't show login button if already authenticated
    }

    const getIcon = () => {
        if (isLoading) return <Icon icon={Loader2} spin />;
        if (provider === 'google') return <GoogleOutlined />;
        if (provider === 'github') return <GithubOutlined />;
        return null;
    };

    return (
        <Button
            onClick={handleLogin}
            loading={isLoading}
            type={type}
            size={size}
            block={block}
            icon={getIcon()}
            className={className}
        >
            {children || `Continue with ${provider.charAt(0).toUpperCase() + provider.slice(1)}`}
        </Button>
    );
}
