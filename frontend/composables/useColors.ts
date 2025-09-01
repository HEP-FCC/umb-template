/**
 * Color Management Composable
 *
 * This composable provides a centralized way to manage colors throughout your application.
 * It ensures consistency and makes it easy to switch between color schemes or themes.
 */

export type CustomColor = "eco" | "earth" | "radiant-blue" | "space" | "flash" | "energy" | "deep-blue";
export type StandardColor = "primary" | "secondary" | "success" | "info" | "warning" | "error" | "neutral";
export type AllColors = CustomColor | StandardColor;

export const useColors = () => {
    // Define your custom color mappings
    const customColors: Record<string, CustomColor> = {
        // Entity types or categories
        environmental: "eco",
        natural: "earth",
        technical: "radiant-blue",
        background: "space",
        highlight: "flash",
        primary: "energy",
        dark: "deep-blue",
    } as const;

    // Define semantic color mappings for different UI states
    const semanticColors = {
        success: "eco" as const,
        locked: "warning" as const,
        active: "energy" as const,
        neutral: "earth" as const,
        information: "radiant-blue" as const,
        background: "space" as const,
        accent: "flash" as const,
    };

    /**
     * Get color for a specific entity type or context
     */
    const getEntityColor = (entityType: string): AllColors => {
        return customColors[entityType] || "neutral";
    };

    /**
     * Get semantic color for UI states
     */
    const getSemanticColor = (semantic: keyof typeof semanticColors): AllColors => {
        return semanticColors[semantic];
    };

    /**
     * Get all available custom colors
     */
    const getCustomColors = (): CustomColor[] => {
        return ["eco", "earth", "radiant-blue", "space", "flash", "energy", "deep-blue"];
    };

    /**
     * Get all available standard colors
     */
    const getStandardColors = (): StandardColor[] => {
        return ["primary", "secondary", "success", "info", "warning", "error", "neutral"];
    };

    /**
     * Check if a color is a custom color
     */
    const isCustomColor = (color: string): color is CustomColor => {
        return getCustomColors().includes(color as CustomColor);
    };

    /**
     * Get CSS variable for a custom color
     */
    const getColorVariable = (color: AllColors, shade: number = 500): string => {
        return `var(--color-${color}-${shade})`;
    };

    /**
     * Theme switching function (for future dark mode support)
     */
    const switchTheme = (theme: "light" | "dark") => {
        // This can be extended to switch between light/dark themes
        // by updating CSS custom properties
        document.documentElement.setAttribute("data-theme", theme);
    };

    return {
        customColors,
        semanticColors,
        getEntityColor,
        getSemanticColor,
        getCustomColors,
        getStandardColors,
        isCustomColor,
        getColorVariable,
        switchTheme,
    };
};
