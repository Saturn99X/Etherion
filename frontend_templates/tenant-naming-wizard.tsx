"""
Tenant Naming Wizard Template

File: frontend / app / onboarding / name - tenant / page.tsx

Full implementation requires Next.js + GraphQL client setup.
"""

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function NameTenantPage() {
    const router = useRouter();
    const [currentSubdomain, setCurrentSubdomain] = useState('');
    const [newSubdomain, setNewSubdomain] = useState('');
    const [validationError, setValidationError] = useState('');
    const [isAvailable, setIsAvailable] = useState<boolean | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        // Get current JWT and extract tenant_subdomain
        const token = localStorage.getItem('access_token');
        if (token) {
            const data = parseJwt(token);
            setCurrentSubdomain(data.tenant_subdomain || '');
            setNewSubdomain(data.tenant_subdomain || '');
        }
    }, []);

    const validateSubdomain = (subdomain: string) => {
        // Client-side validation
        if (subdomain.length < 3) return 'Must be at least 3 characters';
        if (subdomain.length > 12) return 'Must be at most 12 characters';
        if (!/^[a-z]([a-z-]{1,10}[a-z])?$/.test(subdomain)) {
            return 'Lowercase letters and hyphens only';
        }
        return null;
    };

    const checkAvailability = async (subdomain: string) => {
        const error = validateSubdomain(subdomain);
        if (error) {
            setValidationError(error);
            return;
        }

        setValidationError('');
        setIsLoading(true);

        // Check availability via GraphQL
        const token = localStorage.getItem('access_token');
        const response = await fetch('/graphql', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                query: `
          mutation UpdateSubdomain($newSubdomain: String!) {
            updateTenantSubdomain(newSubdomain: $newSubdomain) {
              success
              subdomain
              message
            }
          }
        `,
                variables: { newSubdomain: subdomain }
            })
        });

        const { data, errors } = await response.json();
        setIsLoading(false);

        if (errors || !data.updateTenantSubdomain.success) {
            setValidationError(errors?.[0]?.message || 'Subdomain unavailable');
            setIsAvailable(false);
        } else {
            setIsAvailable(true);
            // Redirect to new subdomain
            window.location.href = `https://${subdomain}.etherionai.com/dashboard`;
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
            <div className="max-w-md w-full bg-white rounded-lg shadow-xl p-8">
                <h1 className="text-3xl font-bold text-gray-900 mb-2">
                    Name Your Workspace
                </h1>
                <p className="text-gray-600 mb-6">
                    Choose a unique subdomain for your team's workspace
                </p>

                <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Current Subdomain
                    </label>
                    <div className="flex items-center bg-gray-100 rounded-md px-4 py-3">
                        <code className="text-sm font-mono">{currentSubdomain}.etherionai.com</code>
                    </div>
                </div>

                <div className="mb-6">
                    <label htmlFor="subdomain" className="block text-sm font-medium text-gray-700 mb-2">
                        New Subdomain
                    </label>
                    <div className="flex items-center">
                        <input
                            id="subdomain"
                            type="text"
                            value={newSubdomain}
                            onChange={(e) => setNewSubdomain(e.target.value.toLowerCase())}
                            className="flex-1 border border-gray-300 rounded-l-md px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="my-company"
                        />
                        <span className="bg-gray-100 border border-l-0 border-gray-300 rounded-r-md px-4 py-3 text-gray-600">
                            .etherionai.com
                        </span>
                    </div>
                    {validationError && (
                        <p className="mt-2 text-sm text-red-600">{validationError}</p>
                    )}
                    {isAvailable === true && (
                        <p className="mt-2 text-sm text-green-600">✓ Available!</p>
                    )}
                </div>

                <button
                    onClick={() => checkAvailability(newSubdomain)}
                    disabled={isLoading || !newSubdomain}
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-md transition-colors disabled:bg-gray-400"
                >
                    {isLoading ? 'Checking...' : 'Continue'}
                </button>

                <p className="mt-4 text-xs text-gray-500 text-center">
                    3-12 characters • Lowercase letters and hyphens only
                </p>
            </div>
        </div>
    );
}

function parseJwt(token: string) {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
        atob(base64)
            .split('')
            .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
            .join('')
    );
    return JSON.parse(jsonPayload);
}
