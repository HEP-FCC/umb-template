/**
 * Badge Color Utilities
 *
 * Provides deterministic color assignment for entity badges that works
 * consistently and doesn't change after navigation loads.
 */

import { APP_CONFIG } from "~/config/app.config";
import type { BadgeColor } from "~/config/app.config";

/**
 * Generate a consistent badge color for a navigation type
 * Uses a predictable order that doesn't change based on config loading state
 */
export function getDeterministicBadgeColor(navType: string): BadgeColor {
    const colors = APP_CONFIG.ui.defaultBadgeColors;
    const navigationOrder = APP_CONFIG.navigationFallback.order;

    // First try to use the navigation order from config if the type exists there
    const orderIndex = navigationOrder.indexOf(navType as (typeof navigationOrder)[number]);
    if (orderIndex !== -1) {
        return colors[orderIndex % colors.length];
    }

    // Fallback to hash-based assignment for unknown types
    let hash = 0;
    for (let i = 0; i < navType.length; i++) {
        const char = navType.charCodeAt(i);
        hash = (hash << 5) - hash + char;
        hash = hash & hash; // Convert to 32-bit integer
    }

    // Use absolute value and modulo to get a consistent index
    const colorIndex = Math.abs(hash) % colors.length;
    return colors[colorIndex];
}

/**
 * Get badge color - always returns consistent deterministic color
 */
export function getBadgeColorWithFallback(navType: string): BadgeColor {
    return getDeterministicBadgeColor(navType);
}

/**
 * Pre-calculate badge colors for navigation types
 */
export function preCalculateBadgeColors(navigationTypes: string[]): Record<string, BadgeColor> {
    const colorMap: Record<string, BadgeColor> = {};

    navigationTypes.forEach((type) => {
        colorMap[type] = getDeterministicBadgeColor(type);
    });

    return colorMap;
}
