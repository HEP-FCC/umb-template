/**
 * Search Preferences Management Composable
 *
 * Manages user preferences for search-related settings including sort field,
 * sort order, and page size. Preferences are stored in a secure, long-lasting
 * cookie for persistence across sessions and page refreshes.
 */

import { APP_CONFIG } from "~/config/app.config";

interface SearchPreferences {
    sortBy: string;
    sortOrder: "asc" | "desc";
    pageSize: number;
    lastUpdated: number;
}

const COOKIE_NAME = `${APP_CONFIG.cookies.namePrefix}-search-preferences`;

// Default values
const DEFAULT_SORT_BY = "created_at";
const DEFAULT_SORT_ORDER: "asc" | "desc" = "desc";
const DEFAULT_PAGE_SIZE = 25;

// Global singleton state for search preferences
const globalSortBy = ref<string>(DEFAULT_SORT_BY);
const globalSortOrder = ref<"asc" | "desc">(DEFAULT_SORT_ORDER);
const globalPageSize = ref<number>(DEFAULT_PAGE_SIZE);
const globalIsLoading = ref(false);
const globalError = ref<string | null>(null);
const isInitialized = ref(false);

/**
 * Composable for managing search display preferences
 */
export const useSearchPreferences = () => {
    /**
     * Initialize preferences from cookie (only once)
     */
    const initializePreferences = () => {
        if (isInitialized.value) return;

        try {
            const preferenceCookie = useCookie<SearchPreferences>(COOKIE_NAME, {
                default: () => ({
                    sortBy: DEFAULT_SORT_BY,
                    sortOrder: DEFAULT_SORT_ORDER,
                    pageSize: DEFAULT_PAGE_SIZE,
                    lastUpdated: Date.now(),
                }),
                secure: process.env.NODE_ENV === "production",
                sameSite: "strict",
                httpOnly: false, // Need client-side access for reactive updates
                maxAge: 60 * 60 * 24, // 1 day
            });

            if (preferenceCookie.value) {
                const prefs = preferenceCookie.value;
                globalSortBy.value = prefs.sortBy || DEFAULT_SORT_BY;
                globalSortOrder.value = prefs.sortOrder || DEFAULT_SORT_ORDER;
                globalPageSize.value = prefs.pageSize || DEFAULT_PAGE_SIZE;
            }
            isInitialized.value = true;
        } catch (err) {
            console.warn("Failed to load search preferences:", err);
            globalError.value = "Failed to load saved search preferences";
            // Use defaults on error
            globalSortBy.value = DEFAULT_SORT_BY;
            globalSortOrder.value = DEFAULT_SORT_ORDER;
            globalPageSize.value = DEFAULT_PAGE_SIZE;
            isInitialized.value = true;
        }
    };

    /**
     * Save preferences to secure cookie
     */
    const savePreferences = () => {
        try {
            const preferences: SearchPreferences = {
                sortBy: globalSortBy.value,
                sortOrder: globalSortOrder.value,
                pageSize: globalPageSize.value,
                lastUpdated: Date.now(),
            };

            const preferenceCookie = useCookie<SearchPreferences>(COOKIE_NAME, {
                default: () => ({
                    sortBy: DEFAULT_SORT_BY,
                    sortOrder: DEFAULT_SORT_ORDER,
                    pageSize: DEFAULT_PAGE_SIZE,
                    lastUpdated: Date.now(),
                }),
                secure: process.env.NODE_ENV === "production",
                sameSite: "strict",
                httpOnly: false,
            });

            preferenceCookie.value = preferences;
            globalError.value = null;
        } catch (err) {
            console.error("Failed to save search preferences:", err);
            globalError.value = "Failed to save search preferences";
        }
    };

    /**
     * Update sort field preference
     */
    const setSortBy = (field: string) => {
        globalSortBy.value = field;
        savePreferences();
    };

    /**
     * Update sort order preference
     */
    const setSortOrder = (order: "asc" | "desc") => {
        globalSortOrder.value = order;
        savePreferences();
    };

    /**
     * Toggle sort order between ascending and descending
     */
    const toggleSortOrder = () => {
        globalSortOrder.value = globalSortOrder.value === "asc" ? "desc" : "asc";
        savePreferences();
    };

    /**
     * Update page size preference
     */
    const setPageSize = (size: number) => {
        // Ensure page size is within reasonable bounds
        const clampedSize = Math.max(20, Math.min(1000, size));
        globalPageSize.value = clampedSize;
        savePreferences();
    };

    /**
     * Update multiple preferences at once
     */
    const updatePreferences = (preferences: Partial<SearchPreferences>) => {
        if (preferences.sortBy !== undefined) {
            globalSortBy.value = preferences.sortBy;
        }
        if (preferences.sortOrder !== undefined) {
            globalSortOrder.value = preferences.sortOrder;
        }
        if (preferences.pageSize !== undefined) {
            globalPageSize.value = Math.max(20, Math.min(1000, preferences.pageSize));
        }
        savePreferences();
    };

    /**
     * Reset all preferences to default values
     */
    const resetToDefaults = () => {
        globalSortBy.value = DEFAULT_SORT_BY;
        globalSortOrder.value = DEFAULT_SORT_ORDER;
        globalPageSize.value = DEFAULT_PAGE_SIZE;
        savePreferences();
    };

    /**
     * Get current preferences as an object
     */
    const getCurrentPreferences = (): SearchPreferences => {
        return {
            sortBy: globalSortBy.value,
            sortOrder: globalSortOrder.value,
            pageSize: globalPageSize.value,
            lastUpdated: Date.now(),
        };
    };

    // Initialize on composable creation
    if (!isInitialized.value) {
        initializePreferences();
    }

    return {
        // Reactive state
        sortBy: readonly(globalSortBy),
        sortOrder: readonly(globalSortOrder),
        pageSize: readonly(globalPageSize),
        isLoading: readonly(globalIsLoading),
        error: readonly(globalError),

        // Actions
        setSortBy,
        setSortOrder,
        toggleSortOrder,
        setPageSize,
        updatePreferences,
        resetToDefaults,
        initializePreferences,

        // Getters
        getCurrentPreferences,

        // Constants for validation
        DEFAULT_SORT_BY,
        DEFAULT_SORT_ORDER,
        DEFAULT_PAGE_SIZE,
    };
};
