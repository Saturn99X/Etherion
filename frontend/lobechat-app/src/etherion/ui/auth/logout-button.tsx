"use client";

import { useState } from 'react';
import { Button } from 'antd';
import { useAuthStore } from '@etherion/stores/auth-store';
import { AuthService } from '@etherion/lib/services/auth-service';
import { Icon } from '@lobehub/ui';
import { LogOut } from 'lucide-react';

interface LogoutButtonProps {
    type?: 'primary' | 'default' | 'text' | 'link';
    size?: 'small' | 'middle' | 'large';
    className?: string;
    showText?: boolean;
}

export function LogoutButton({
    type = 'text',
    size = 'middle',
    className = '',
    showText = true
}: LogoutButtonProps) {
    const [isLoading, setIsLoading] = useState(false);
    const { isAuthenticated, logout } = useAuthStore();

    const handleLogout = async () => {
        if (!isAuthenticated) return;

        setIsLoading(true);
        try {
            await AuthService.logout();
            logout();
        } catch (error) {
            console.error('Logout error:', error);
            // Still logout locally even if server logout fails
            logout();
        } finally {
            setIsLoading(false);
        }
    };

    if (!isAuthenticated) {
        return null; // Don't show logout button if not authenticated
    }

    return (
        <Button
            onClick={handleLogout}
            loading={isLoading}
            type={type}
            size={size}
            icon={<Icon icon={LogOut} />}
            className={className}
        >
            {showText && (isLoading ? 'Signing out...' : 'Sign out')}
        </Button>
    );
}
