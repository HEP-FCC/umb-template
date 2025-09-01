/**
 * Navigation Configuration Management
 *
 * This composable manages the dynamic fetching of navigation configuration
 * from the backend schema endpoint. All UI elements (colors, icons, labels)
 * are derived from app config, not from backend.
 */

import type { SchemaInfo } from "~/types/schema";
import { APP_CONFIG } from "~/config/app.config";

interface NavigationConfig {
    order: string[];
    menu: Record<
        string,
        {
            columnName: string;
            orderIndex: number;
        }
    >;
}

// Global singleton state to prevent multiple API calls
const globalNavigationConfig = ref<NavigationConfig>({
    order: [],
    menu: {},
});

const globalIsLoading = ref(false);
const globalError = ref<string | null>(null);

// Global cache for preloaded dropdown data
let preloadedDropdownCache: Record<string, unknown[]> = {};

/**
 * Get preloaded dropdown data for a specific type
 * This is used by useNavigationState to check for cached data
 */
export const getPreloadedDropdownData = (type: string): unknown[] | null => {
    return preloadedDropdownCache[type] || null;
};

/**
 * Clear preloaded dropdown cache
 */
export const clearPreloadedDropdownCache = (): void => {
    preloadedDropdownCache = {};
};

export const useNavigationConfig = () => {
    const { getSchema } = useSchema();

    // Use global singleton state
    const navigationConfig = globalNavigationConfig;
    const isLoading = globalIsLoading;
    const error = globalError;

    /**
     * Fetch navigation configuration from backend schema endpoint
     */
    const fetchNavigationConfig = async (): Promise<void> => {
        if (isLoading.value) return;

        try {
            isLoading.value = true;
            error.value = null;

            const response = (await getSchema()) as unknown as SchemaInfo;

            if (response.navigation_config) {
                navigationConfig.value = {
                    order: response.navigation_config.order || [],
                    menu: response.navigation_config.menu || {},
                };
            } else {
                // Fallback: use foreign_keys as navigation order if no config
                const foreignKeys = response.foreign_keys || [];
                const fallbackMenu: Record<string, { columnName: string; orderIndex: number }> = {};

                foreignKeys.forEach((fk: string, index: number) => {
                    const key = fk.replace("_id", "");
                    fallbackMenu[key] = {
                        columnName: fk,
                        orderIndex: index,
                    };
                });

                navigationConfig.value = {
                    order: foreignKeys.map((fk: string) => fk.replace("_id", "")),
                    menu: fallbackMenu,
                };
            }
        } catch (err) {
            error.value = err instanceof Error ? err.message : "Failed to fetch navigation config";
            console.error("Failed to fetch navigation configuration:", err);

            // Fallback to empty configuration
            navigationConfig.value = {
                order: [],
                menu: {},
            };
        } finally {
            isLoading.value = false;
        }
    };

    // Initialize on first use only if not already loaded and not currently loading
    if (navigationConfig.value.order.length === 0 && !isLoading.value) {
        fetchNavigationConfig();
    }

    /**
     * Get navigation order
     */
    const getNavigationOrder = (): string[] => {
        return navigationConfig.value.order;
    };

    /**
     * Check if navigation configuration is ready
     */
    const isNavigationReady = (): boolean => {
        return !isLoading.value && navigationConfig.value.order.length > 0;
    };

    /**
     * Get navigation menu configuration
     */
    const getNavigationMenu = () => {
        return navigationConfig.value.menu;
    };

    /**
     * Get configuration for a specific navigation type with derived UI elements
     */
    const getNavigationItem = (type: string) => {
        const menuConfig = navigationConfig.value.menu[type];

        if (!menuConfig) {
            throw new Error(
                `Navigation type '${type}' not found in configuration. Available types: ${Object.keys(
                    navigationConfig.value.menu,
                ).join(", ")}. Is navigation initialized?`,
            );
        }

        const orderIndex = menuConfig.orderIndex;
        const colors = APP_CONFIG.ui.defaultBadgeColors;

        return {
            icon: APP_CONFIG.ui.defaultIcon, // Use hardcoded folder icon for all items
            label: type.charAt(0).toUpperCase() + type.slice(1).replace(/[_-]/g, " "),
            badgeColor: colors[orderIndex % colors.length],
            columnName: menuConfig.columnName,
        };
    };

    /**
     * Preload dropdown data for all navigation types concurrently
     * This actually populates the useNavigationState cache to avoid on-demand loading
     */
    const preloadDropdownData = async (): Promise<void> => {
        const { getDropdownOptions } = useApiClient();
        const order = navigationConfig.value.order;

        if (order.length === 0) {
            return;
        }

        try {
            // Create concurrent API calls for all navigation types
            const preloadPromises = order.map(async (type: string) => {
                try {
                    const items = await getDropdownOptions(type);

                    // Store the preloaded data in module cache
                    preloadedDropdownCache[type] = items;

                    return { type, success: true, count: items.length };
                } catch (error) {
                    console.warn(`Error preloading ${type}:`, error);
                    return { type, success: false, error };
                }
            });

            // Wait for all preload operations to complete
            const _results = await Promise.allSettled(preloadPromises);
        } catch (error) {
            console.warn("Error during dropdown preloading:", error);
        }
    };

    /**
     * Initialize navigation configuration if not already loaded
     */
    const initializeNavigation = async (): Promise<void> => {
        if (navigationConfig.value.order.length === 0) {
            await fetchNavigationConfig();
            // Note: Dropdown preloading is now handled by useNavigationState
        }
    };

    return {
        navigationConfig: readonly(navigationConfig),
        isLoading: readonly(isLoading),
        error: readonly(error),
        isNavigationReady,
        fetchNavigationConfig,
        getNavigationOrder,
        getNavigationMenu,
        getNavigationItem,
        initializeNavigation,
        preloadDropdownData,
    };
};
