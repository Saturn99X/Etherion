"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/lib/stores/auth-store';
import { AuthService } from '@/lib/services/auth-service';
import { LogOut } from 'lucide-react';

interface LogoutButtonProps {
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
  className?: string;
  showText?: boolean;
}

export function LogoutButton({
  variant = 'ghost',
  size = 'default',
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
      disabled={isLoading}
      variant={variant}
      size={size}
      className={`gap-2 ${className}`}
    >
      {isLoading ? (
        <>
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          {showText && 'Signing out...'}
        </>
      ) : (
        <>
          <LogOut className="h-4 w-4" />
          {showText && 'Sign out'}
        </>
      )}
    </Button>
  );
}
