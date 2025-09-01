// Auto-imported: ref, computed, readonly, watchEffect, type Ref
import type { DropdownItem } from "~/types/schema";
// Auto-imported: useNavigationConfig, getPreloadedDropdownData

/**
 * Dynamic navigation state management with schema-driven configuration
 */
export function useNavigationState() {
    const { baseUrl: _baseUrl, apiGet } = useApiClient();
    const { getNavigationOrder, getNavigationItem, initializeNavigation, isNavigationReady } = useNavigationConfig();

    // Dynamic refs based on navigation order
    const navigationOrder = computed(() => getNavigationOrder());

    // Create dynamic refs for each navigation type
    const itemsRefs: Record<string, Ref<DropdownItem[]>> = {};
    const loadingRefs: Record<string, Ref<boolean>> = {};
    const openRefs: Record<string, Ref<boolean>> = {};
    const fetchedRefs: Record<string, Ref<boolean>> = {}; // Track successful fetches (even if empty)

    // Initialize navigation and setup refs
    const initializeRefs = () => {
        const order = navigationOrder.value;
        order.forEach((type) => {
            if (!itemsRefs[type]) {
                itemsRefs[type] = ref<DropdownItem[]>([]);
                loadingRefs[type] = ref(false);
                openRefs[type] = ref(false);
                fetchedRefs[type] = ref(false); // Track if this dropdown has been successfully fetched
            }
        });
    };

    // Initialize navigation configuration and refs
    initializeNavigation().then(() => {
        initializeRefs();
        proactivelyLoadDropdownData();
    });

    // Also watch for changes in navigation order and update refs accordingly
    watchEffect(() => {
        const order = navigationOrder.value;
        if (order.length > 0) {
            initializeRefs();
            // Load dropdown data when navigation becomes ready
            if (isNavigationReady()) {
                proactivelyLoadDropdownData();
            }
        }
    });

    // Computed dropdowns object
    const dropdowns = computed(() => {
        const result: Record<
            string,
            {
                items: DropdownItem[];
                isLoading: boolean;
                isOpen: boolean;
                icon: string;
                label: string;
                clearLabel: string;
            }
        > = {};

        // Only process navigation if config is ready and we have navigation order
        if (isNavigationReady() && navigationOrder.value.length > 0) {
            try {
                navigationOrder.value.forEach((type) => {
                    const config = getNavigationItem(type);
                    result[type] = {
                        items: itemsRefs[type]?.value || [],
                        isLoading: loadingRefs[type]?.value || false,
                        isOpen: openRefs[type]?.value || false,
                        icon: config.icon,
                        label: config.label,
                        clearLabel: `clear selection`,
                    };
                });
            } catch (error) {
                console.error("Error building dropdowns configuration:", error);
                // Return empty object if there's an error
                return {};
            }
        }

        return result;
    });

    function getItemsRef(type: string): Ref<DropdownItem[]> | null {
        const result = itemsRefs[type] || null;
        return result;
    }

    function getLoadingRef(type: string): Ref<boolean> | null {
        const result = loadingRefs[type] || null;
        return result;
    }

    function getOpenRef(type: string): Ref<boolean> | null {
        return openRefs[type] || null;
    }

    /**
     * Proactively load dropdown data in the background for better UX
     * Loads multiple dropdown levels concurrently when possible
     */
    async function proactivelyLoadDropdownData(currentPath: Record<string, string | null> = {}) {
        if (!isNavigationReady() || navigationOrder.value.length === 0) {
            return;
        }

        const order = navigationOrder.value;

        try {
            // Always load the first level immediately (no dependencies)
            const firstLevelType = order[0];
            const firstLevelPromise = loadSingleDropdownLevel(firstLevelType, {});

            // Find the deepest level that has a value
            let deepestFilledLevel = -1;
            for (let i = 0; i < order.length; i++) {
                const type = order[i];
                if (currentPath[type]) {
                    deepestFilledLevel = i;
                } else {
                    break;
                }
            }

            // Create concurrent promises for levels that can be loaded
            const loadPromises: Promise<void>[] = [firstLevelPromise];

            // If we have path data, load the next level after the deepest filled level
            if (deepestFilledLevel >= 0 && deepestFilledLevel + 1 < order.length) {
                const nextLevelType = order[deepestFilledLevel + 1];
                const filters = buildFiltersForLevel(currentPath, deepestFilledLevel + 1);
                loadPromises.push(loadSingleDropdownLevel(nextLevelType, filters));
            }

            // Run all possible loads concurrently
            await Promise.allSettled(loadPromises);
        } catch (error) {
            console.warn("Error during proactive dropdown loading:", error);
        }
    }

    /**
     * Load a single dropdown level with given filters
     */
    async function loadSingleDropdownLevel(type: string, filters: Record<string, string> = {}) {
        const itemsRef = getItemsRef(type);
        const loadingRef = getLoadingRef(type);
        const fetchedRef = fetchedRefs[type];

        // Only load if not already fetched successfully (even if empty) or loading
        if (!itemsRef || !loadingRef || !fetchedRef || fetchedRef.value || loadingRef.value) {
            return;
        }

        try {
            // Check for preloaded data first (only for first level without filters)
            if (Object.keys(filters).length === 0) {
                const preloadedData = getPreloadedDropdownData(type);
                if (preloadedData && preloadedData.length > 0) {
                    itemsRef.value = preloadedData as DropdownItem[];
                    fetchedRef.value = true; // Mark as successfully fetched
                    return;
                }
            }

            // Fetch from API with appropriate filters
            loadingRef.value = true;

            let requestUrl = `/dropdown/${type}`;
            if (Object.keys(filters).length > 0) {
                const params = new URLSearchParams();
                const filterObj: Record<string, string> = {};
                Object.entries(filters).forEach(([key, value]) => {
                    if (value?.trim()) {
                        const filterKey = key.endsWith("_name") ? key : `${key}_name`;
                        filterObj[filterKey] = value;
                    }
                });

                if (Object.keys(filterObj).length > 0) {
                    params.append("filters", JSON.stringify(filterObj));
                    requestUrl += `?${params.toString()}`;
                }
            }

            // Use the enhanced API client with automatic token refresh
            const data = await apiGet<{ data: DropdownItem[] }>(requestUrl);
            const items = data.data || [];
            itemsRef.value = items;
            fetchedRef.value = true; // Mark as successfully fetched (even if empty)
        } catch (error) {
            console.warn(`Error loading ${type}:`, error);
            // Don't mark as fetched on error - allow retry later
        } finally {
            if (loadingRef) {
                loadingRef.value = false;
            }
        }
    }

    /**
     * Build filters for a specific level based on current path
     */
    function buildFiltersForLevel(currentPath: Record<string, string | null>, level: number): Record<string, string> {
        const order = navigationOrder.value;
        const filters: Record<string, string> = {};

        for (let i = 0; i < level; i++) {
            const filterType = order[i];
            const filterValue = currentPath[filterType];
            if (filterValue) {
                filters[filterType] = filterValue;
            }
        }

        return filters;
    }

    async function loadDropdownData(type: string, filters: Record<string, string> = {}, forceReload: boolean = false) {
        // Ensure navigation is initialized first
        await initializeNavigation();

        const itemsRef = getItemsRef(type);
        const loadingRef = getLoadingRef(type);
        const fetchedRef = fetchedRefs[type];

        if (!itemsRef || !loadingRef || !fetchedRef) {
            console.warn(`Unknown navigation type: ${type}`, { itemsRef, loadingRef, fetchedRef });
            return;
        }

        // Skip if already loading
        if (loadingRef.value) {
            return;
        }

        // Check for preloaded data first (only if no filters and no force reload)
        const hasFilters = Object.keys(filters).length > 0;
        if (!forceReload && !hasFilters) {
            // First check if we have preloaded data available
            const preloadedData = getPreloadedDropdownData(type);
            if (preloadedData && preloadedData.length > 0) {
                itemsRef.value = preloadedData as DropdownItem[];
                fetchedRef.value = true; // Mark as successfully fetched
                return; // Exit early, no need to make API call
            }

            // If no preloaded data but already successfully fetched (even if empty), skip API call
            if (fetchedRef.value) {
                return;
            }
        }

        // If force reload, reset the fetched state
        if (forceReload) {
            fetchedRef.value = false;
        }

        loadingRef.value = true;

        try {
            // Use the new generic API endpoint directly
            let requestUrl = `/dropdown/${type}`;

            if (Object.keys(filters).length > 0) {
                const params = new URLSearchParams();
                // Convert filters to the format expected by the new endpoint
                const filterObj: Record<string, string> = {};
                Object.entries(filters).forEach(([key, value]) => {
                    if (value?.trim()) {
                        // Convert from type to type_name for the backend filter
                        const filterKey = key.endsWith("_name") ? key : `${key}_name`;
                        filterObj[filterKey] = value;
                    }
                });

                if (Object.keys(filterObj).length > 0) {
                    params.append("filters", JSON.stringify(filterObj));
                    requestUrl += `?${params.toString()}`;
                }
            }

            // Use the enhanced API client with automatic token refresh
            const data = await apiGet<{ data: DropdownItem[] }>(requestUrl);
            itemsRef.value = data.data || [];
            fetchedRef.value = true; // Mark as successfully fetched (even if empty)
        } catch (error) {
            console.error(`Error loading ${type}:`, error);
            itemsRef.value = [];
            // Don't mark as fetched on error - allow retry later
        } finally {
            loadingRef.value = false;
        }
    }

    /**
     * Load dropdown cascade efficiently with concurrent requests where possible
     * This optimizes the loading of dependent dropdowns by batching independent calls
     */
    async function loadDropdownCascade(currentPath: Record<string, string | null> = {}) {
        if (!isNavigationReady() || navigationOrder.value.length === 0) {
            return;
        }

        const order = navigationOrder.value;
        const loadPromises: Promise<void>[] = [];

        // Always load the first level (independent)
        loadPromises.push(loadSingleDropdownLevel(order[0], {}));

        // For each subsequent level, check if we have enough path data to load it
        for (let level = 1; level < order.length; level++) {
            const type = order[level];
            const filters = buildFiltersForLevel(currentPath, level);

            // Only load if we have all required filters for this level
            if (Object.keys(filters).length === level) {
                loadPromises.push(loadSingleDropdownLevel(type, filters));
            } else {
                // If we can't load this level, we can't load any subsequent levels
                break;
            }
        }

        // Run all possible loads concurrently
        try {
            await Promise.allSettled(loadPromises);
        } catch (error) {
            console.warn("Error during dropdown cascade loading:", error);
        }
    }

    /**
     * Priority loading: Navigation dropdowns first, then other content
     * This ensures navigation UI is responsive immediately
     */
    async function loadNavigationWithPriority(currentPath: Record<string, string | null> = {}) {
        if (!isNavigationReady() || navigationOrder.value.length === 0) {
            return;
        }

        try {
            // High priority: Load first level immediately (always available)
            const order = navigationOrder.value;
            const firstLevelType = order[0];

            // Start first level loading immediately
            await loadSingleDropdownLevel(firstLevelType, {});

            // Medium priority: Load subsequent levels based on current path
            const cascadePromises: Promise<void>[] = [];
            for (let level = 1; level < order.length; level++) {
                const type = order[level];
                const filters = buildFiltersForLevel(currentPath, level);

                if (Object.keys(filters).length === level) {
                    cascadePromises.push(loadSingleDropdownLevel(type, filters));
                } else {
                    break;
                }
            }

            // Load remaining levels concurrently (but after first level is done)
            if (cascadePromises.length > 0) {
                await Promise.allSettled(cascadePromises);
            }
        } catch (error) {
            console.warn("Error during priority navigation loading:", error);
        }
    }
    function toggleDropdown(type: string) {
        const openRef = getOpenRef(type);
        if (!openRef) {
            return;
        }

        const wasOpen = openRef.value;

        // Close all dropdowns
        closeAllDropdowns();

        // Open the clicked one if it wasn't already open
        if (!wasOpen) {
            openRef.value = true;
        }
    }

    function closeAllDropdowns() {
        const order = navigationOrder.value;
        order.forEach((type: string) => {
            const openRef = getOpenRef(type);
            if (openRef) {
                openRef.value = false;
            }
        });
    }

    function clearDropdownData(type: string) {
        const itemsRef = getItemsRef(type);
        const fetchedRef = fetchedRefs[type];
        if (itemsRef) {
            itemsRef.value = [];
        }
        if (fetchedRef) {
            fetchedRef.value = false; // Reset fetched state to allow new fetch
        }
    }

    function clearDependentDropdowns(changedType: string) {
        const order = navigationOrder.value;
        const typeIndex = order.indexOf(changedType);
        if (typeIndex === -1) return;

        // Clear all subsequent navigation types
        for (let i = typeIndex + 1; i < order.length; i++) {
            const dependentType = order[i];
            const itemsRef = getItemsRef(dependentType);
            const fetchedRef = fetchedRefs[dependentType];
            if (itemsRef) {
                itemsRef.value = [];
            }
            if (fetchedRef) {
                fetchedRef.value = false; // Reset fetched state to allow new fetch with updated filters
            }
        }
    }

    // Utility functions for compatibility
    function getItems(type: string): DropdownItem[] {
        const itemsRef = getItemsRef(type);
        return itemsRef ? itemsRef.value : [];
    }

    function isLoading(type: string): boolean {
        const loadingRef = getLoadingRef(type);
        return loadingRef ? loadingRef.value : false;
    }

    function isOpen(type: string): boolean {
        const openRef = getOpenRef(type);
        return openRef ? openRef.value : false;
    }

    return {
        dropdowns,
        itemsRefs: readonly(itemsRefs),
        loadingRefs: readonly(loadingRefs),
        openRefs: readonly(openRefs),
        loadDropdownData,
        loadDropdownCascade,
        loadNavigationWithPriority,
        toggleDropdown,
        closeAllDropdowns,
        clearDropdownData,
        clearDependentDropdowns,
        getItems,
        isLoading,
        isOpen,
        navigationOrder,
        proactivelyLoadDropdownData,
    };
}
