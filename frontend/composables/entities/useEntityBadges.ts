/**
 * Entity Badge Management Composable
 *
 * Provides optimized badge color assignment and caching to prevent
 * the gray->colored flash when entities load before navigation config.
 */

import type { Entity } from "~/types/entity";
import type { BadgeColor } from "~/config/app.config";
import { getDeterministicBadgeColor } from "~/utils/badgeColors";

interface BadgeInfo {
    key: string;
    label: string;
    value: string;
    color: BadgeColor;
    filterKey: string;
}

/**
 * Composable for managing entity badges with optimized color assignment
 */
export const useEntityBadges = () => {
    const { getNavigationItem, getNavigationOrder } = useNavigationConfig();
    const { formatFieldName } = useUtils();
    const { getMetadataBadges } = useMetadataPreferences();

    // Cache for badge colors to avoid recalculation
    const badgeColorCache = new Map<string, BadgeColor>();

    /**
     * Clear the badge color cache (useful when navigation config changes)
     */
    const clearBadgeColorCache = () => {
        badgeColorCache.clear();
    };

    /**
     * Get optimized badge color for a navigation type
     */
    const getBadgeColor = (navType: string): BadgeColor => {
        // Check cache first
        if (badgeColorCache.has(navType)) {
            return badgeColorCache.get(navType)!;
        }

        // Always use deterministic color for consistency
        const color = getDeterministicBadgeColor(navType);

        // Cache the result
        badgeColorCache.set(navType, color);
        return color;
    };

    /**
     * Get all badge information for an entity
     */
    const getEntityBadges = (entity: Entity, activeFilters?: Record<string, string>): BadgeInfo[] => {
        // Get the navigation order to determine which fields are valid navigation fields
        const navigationOrder = getNavigationOrder();

        // Generate navigation badges only for fields that are actual navigation fields
        const navigationBadges = Object.entries(entity)
            .filter(([key, value]) => {
                // Check if field ends with '_name' and has a value
                if (!key.endsWith("_name") || !value || typeof value !== "string" || value.trim() === "") {
                    return false;
                }

                // Check if the navigation type (without '_name') is a valid navigation field
                const navType = key.replace("_name", "");
                return navigationOrder.includes(navType);
            })
            .map(([key, value]) => {
                const navType = key.replace("_name", "");
                const color = getBadgeColor(navType);

                // Get label from navigation config or use formatted fallback
                let label: string;
                try {
                    const config = getNavigationItem(navType);
                    label = config.label;
                } catch {
                    label = formatFieldName(navType);
                }

                return {
                    key: navType ? String(navType) : "unknown",
                    label: String(label || formatFieldName(navType || "unknown")),
                    value: String(value || ""),
                    color,
                    filterKey: key,
                };
            })
            .filter((badge) => {
                // Filter out badges that match currently active filters
                const activeFilterValue = activeFilters?.[badge.filterKey];
                return !activeFilterValue || activeFilterValue !== badge.value;
            });

        // Add metadata badges from user preferences (includes status if user selects it)
        const metadataBadges = getMetadataBadges(entity).map((metadataBadge) => ({
            key: metadataBadge.key,
            label: metadataBadge.label,
            value: metadataBadge.value,
            color: metadataBadge.color as BadgeColor,
            filterKey: `metadata_${metadataBadge.key}`, // Not used for filtering but kept for consistency
        }));

        return [...navigationBadges, ...metadataBadges];
    };

    /**
     * Preload badge colors for known navigation types
     * This can be called early to warm up the cache
     */
    const preloadBadgeColors = (navigationTypes: string[]) => {
        navigationTypes.forEach((type) => {
            getBadgeColor(type);
        });
    };

    return {
        getEntityBadges,
        getBadgeColor,
        clearBadgeColorCache,
        preloadBadgeColors,
    };
};
