"use client";

import { ActionIcon } from "@lobehub/ui";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "./theme-provider";

export function ThemeSwitcher() {
    const { theme, toggleTheme } = useTheme();

    return (
        <ActionIcon
            icon={theme === "dark" ? Sun : Moon}
            onClick={toggleTheme}
            title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
            tooltipProps={{ placement: "bottom" }}
        />
    );
}
