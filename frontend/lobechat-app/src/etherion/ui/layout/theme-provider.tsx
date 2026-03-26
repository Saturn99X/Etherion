"use client";

import React from "react";
import { useThemeMode } from "antd-style";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    // LobeChat already provides the theme context via its GlobalLayout.
    // This wrapper is a no-op to satisfy Etherion component imports.
    return <>{children}</>;
}

export function useTheme() {
    const { themeMode, setThemeMode } = useThemeMode();

    const toggleTheme = () => {
        setThemeMode(themeMode === 'dark' ? 'light' : 'dark');
    };

    return {
        theme: (themeMode === 'auto' ? 'dark' : themeMode) as "dark" | "light",
        setTheme: (t: "dark" | "light") => setThemeMode(t),
        toggleTheme
    };
}
