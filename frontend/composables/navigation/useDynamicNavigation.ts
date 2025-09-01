/**
 * Dynamic Navigation Utilities
 *
 * These utilities work with the schema-driven navigation system and automatically
 * adapt to any database structure. They replace the hardcoded navigation logic
 * with flexible, configuration-driven alternatives.
 */

import { APP_CONFIG } from "~/config/app.config";

/**
 * Composable for dynamic navigation functionality
 */
export const useDynamicNavigation = () => {
    const { getNavigationOrder, getNavigationItem, initializeNavigation } = useNavigationConfig();

    /**
     * Get navigation order from dynamic config (sync version)
     */
    const getNavigationOrderSync = () => {
        return getNavigationOrder();
    };

    /**
     * Parse route parameters into a path object using dynamic navigation order
     */
    const parseRouteToPath = (routeParams: string[]): Record<string, string | null> => {
        const order = getNavigationOrder();
        const pathObj: Record<string, string | null> = {};

        order.forEach((type: string, index: number) => {
            pathObj[type] = routeParams[index] || null;
        });

        return pathObj;
    };

    /**
     * Parse route parameters into API filters using dynamic navigation order
     */
    const parseRouteToFilters = (routeParams: string[]): Record<string, string> => {
        const order = getNavigationOrder();
        const filters: Record<string, string> = {};

        order.forEach((type: string, index: number) => {
            if (routeParams.length > index && routeParams[index]) {
                const filterKey = `${type}_name`;
                filters[filterKey] = routeParams[index];
            }
        });

        return filters;
    };

    /**
     * Build navigation URL from current path, replacing one navigation type
     */
    const buildNavigationUrl = (
        currentPath: Record<string, string | null>,
        type: string,
        value: string | null,
    ): string => {
        const order = getNavigationOrder();

        // Create new path with updated value
        const newPath = { ...currentPath };
        newPath[type] = value;

        // Clear dependent navigation items (ones that come after this one)
        const typeIndex = order.findIndex((t) => t === type);
        if (typeIndex !== -1) {
            for (let i = typeIndex + 1; i < order.length; i++) {
                newPath[order[i]] = null;
            }
        }

        // Build URL path parts, filtering out null values
        const newPathParts = order.map((t: string) => newPath[t]);
        const filteredParts = newPathParts.filter((p: string | null) => p);

        return `/${filteredParts.join("/")}`;
    };

    /**
     * Clear navigation from a specific point onwards
     */
    const clearNavigationFrom = (currentPath: Record<string, string | null>, fromType: string): string => {
        const order = getNavigationOrder();

        const typeIndex = order.findIndex((t) => t === fromType);
        if (typeIndex === -1) return "/";

        // Clear all navigation from this point onwards
        const pathParts = order.map((t: string) => currentPath[t]);
        const newPathParts = pathParts.slice(0, typeIndex).filter((p: string | null) => p);

        return newPathParts.length > 0 ? `/${newPathParts.join("/")}` : "/";
    };

    /**
     * Build filters for a specific navigation dropdown
     */
    const buildDropdownFilters = (
        currentPath: Record<string, string | null>,
        forType: string,
    ): Record<string, string> => {
        const order = getNavigationOrder();
        const filters: Record<string, string> = {};

        // Add filters for all navigation types that come before this one
        order.forEach((type: string) => {
            if (type !== forType && currentPath[type]) {
                const filterKey = `${type}_name`;
                filters[filterKey] = currentPath[type]!;
            }
        });

        return filters;
    };

    /**
     * Get navigation breadcrumbs
     */
    const getBreadcrumbs = (currentPath: Record<string, string | null>) => {
        const order = getNavigationOrder();
        const breadcrumbs: Array<{ label: string; url: string; type: string }> = [];

        const cumulativePath: string[] = [];

        for (const type of order) {
            if (currentPath[type]) {
                cumulativePath.push(currentPath[type]!);
                const navigationConfig = getNavigationItem(type);

                breadcrumbs.push({
                    label: navigationConfig.label,
                    url: `/${cumulativePath.join("/")}`,
                    type,
                });
            }
        }

        return breadcrumbs;
    };

    /**
     * Get current page title based on navigation path
     */
    const getPageTitle = (currentPath: Record<string, string | null>): string => {
        const order = getNavigationOrder();

        // Find the deepest navigation level
        let deepestType: string | null = null;
        let deepestValue: string | null = null;

        order.forEach((type: string) => {
            if (currentPath[type]) {
                deepestType = type;
                deepestValue = currentPath[type];
            }
        });

        if (deepestType && deepestValue) {
            const navigationConfig = getNavigationItem(deepestType);
            return `${navigationConfig.label}: ${deepestValue}`;
        }

        return APP_CONFIG.branding.title;
    };

    /**
     * Parse URL slug into navigation path
     */
    const parseSlugToPath = (slug: string[]): Record<string, string | null> => {
        const order = getNavigationOrder();
        const pathObj: Record<string, string | null> = {};

        order.forEach((type: string, index: number) => {
            pathObj[type] = slug[index] || null;
        });

        return pathObj;
    };

    /**
     * Get valid next navigation options
     */
    const getNextNavigationOptions = (currentPath: Record<string, string | null>) => {
        const order = getNavigationOrder();

        // Find the next navigation type that needs to be filled
        for (const type of order) {
            if (!currentPath[type]) {
                return type;
            }
        }

        return null; // All navigation levels are filled
    };

    /**
     * Validate navigation path structure
     */
    const validatePath = (pathObj: Record<string, string | null>): boolean => {
        const order = getNavigationOrder();

        // Ensure path follows the correct order (no gaps)
        let foundEmpty = false;
        for (const type of order) {
            if (!pathObj[type]) {
                foundEmpty = true;
            } else if (foundEmpty) {
                // Found a value after an empty slot - invalid
                return false;
            }
        }

        return true;
    };

    return {
        getNavigationOrder: getNavigationOrderSync,
        parseRouteToPath,
        parseRouteToFilters,
        buildNavigationUrl,
        clearNavigationFrom,
        buildDropdownFilters,
        getBreadcrumbs,
        getPageTitle,
        parseSlugToPath,
        getNextNavigationOptions,
        validatePath,
        initializeNavigation,
    };
};
