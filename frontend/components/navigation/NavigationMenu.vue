<template>
    <div class="mb-6 bg-space-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-0">
            <nav class="flex space-x-8 py-4">
                <!-- Loading state while navigation config is not ready -->
                <div v-if="!isNavigationReady" class="flex space-x-4">
                    <div class="animate-pulse">
                        <div class="h-10 w-32 bg-space-200 rounded" />
                    </div>
                </div>

                <!-- Dynamic Navigation Dropdowns -->
                <template v-for="(type, index) in navigationOrder" v-else :key="type">
                    <div
                        v-if="(index === 0 || currentPath[navigationOrder[index - 1]]) && dropdowns[type]"
                        class="relative dropdown-container"
                    >
                        <UButton
                            :color="currentPath[type] ? 'primary' : 'neutral'"
                            :variant="currentPath[type] ? 'solid' : 'ghost'"
                            trailing-icon="i-heroicons-chevron-down-20-solid"
                            class="transition-all duration-150 cursor-pointer"
                            size="lg"
                            @click="handleToggleDropdown(type)"
                        >
                            <!-- Conditional icon: loading spinner or folder -->
                            <UIcon
                                v-if="dropdowns[type]?.isLoading && !dropdowns[type]?.items?.length"
                                name="i-heroicons-arrow-path"
                                class="mr-2 animate-spin"
                            />
                            <UIcon v-else name="i-heroicons-folder" class="mr-2" />
                            {{ currentPath[type] || dropdowns[type]?.label || type }}
                        </UButton>

                        <transition
                            enter-active-class="transition ease-out duration-100"
                            enter-from-class="transform opacity-0 scale-95"
                            enter-to-class="transform opacity-100 scale-100"
                            leave-active-class="transition ease-in duration-75"
                            leave-from-class="transform opacity-100 scale-100"
                            leave-to-class="transform opacity-0 scale-95"
                        >
                            <div
                                v-if="dropdowns[type]?.isOpen"
                                class="absolute top-full left-0 mt-1 w-auto min-w-48 max-w-sm bg-white border border-space-200 rounded-md shadow-lg z-50 dropdown-menu max-h-120 overflow-y-auto"
                            >
                                <div class="p-2">
                                    <div v-if="currentPath[type]" class="mb-2">
                                        <button
                                            class="w-full text-left px-3 py-2 text-deep-blue-400 text-sm hover:bg-space-50 rounded flex items-center whitespace-nowrap"
                                            @click="handleClearSelection(type)"
                                        >
                                            <UIcon name="i-heroicons-x-mark" class="mr-2" />
                                            {{ dropdowns[type]?.clearLabel || `clear ${type.toLowerCase()}` }}
                                        </button>
                                    </div>

                                    <!-- Show loading only if no items AND currently loading -->
                                    <div
                                        v-if="!dropdowns[type]?.items?.length && dropdowns[type]?.isLoading"
                                        class="p-2"
                                    >
                                        <USkeleton class="h-4 w-24" />
                                        <USkeleton class="h-4 w-32 mt-1" />
                                        <USkeleton class="h-4 w-28 mt-1" />
                                    </div>

                                    <!-- Show items if available (even while loading more) -->
                                    <div v-else class="space-y-1">
                                        <button
                                            v-for="item in dropdowns[type]?.items || []"
                                            :key="item.entity_id"
                                            class="w-full text-left px-3 py-2 text-sm hover:bg-deep-blue-50 rounded transition-colors duration-150 block truncate"
                                            style="max-width: 300px"
                                            :class="{
                                                'bg-space-200': currentPath[type] === item.name,
                                            }"
                                            :title="item.name"
                                            @click="handleNavigate(type, item.name)"
                                        >
                                            {{ item.name }}
                                        </button>

                                        <!-- Show a subtle loading indicator at the bottom if still loading but have items -->
                                        <div
                                            v-if="dropdowns[type]?.items?.length && dropdowns[type]?.isLoading"
                                            class="px-3 py-1"
                                        >
                                            <div class="flex items-center text-xs">
                                                <div
                                                    class="animate-spin rounded-full h-3 w-3 border border-space-300 border-t-transparent mr-2"
                                                />
                                                Loading...
                                            </div>
                                        </div>

                                        <div
                                            v-if="!dropdowns[type]?.items?.length && !dropdowns[type]?.isLoading"
                                            class="px-3 py-2 text-sm"
                                        >
                                            No options available.
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </transition>
                    </div>
                </template>
            </nav>
        </div>
    </div>
</template>

<script setup lang="ts">
// Auto-imported: watchEffect, ref, onMounted, onUnmounted, computed
// Auto-imported: useNavigationState, useNavigationConfig, useDynamicNavigation

interface Props {
    routeParams: string[];
}

const props = defineProps<Props>();

const {
    dropdowns,
    navigationOrder,
    loadDropdownData,
    loadNavigationWithPriority,
    toggleDropdown,
    closeAllDropdowns,
    clearDependentDropdowns,
    getItems,
    isLoading,
    isOpen,
    proactivelyLoadDropdownData,
} = useNavigationState();

const { parseRouteToPath, buildNavigationUrl, clearNavigationFrom, initializeNavigation } = useDynamicNavigation();

// Add navigation ready state from useNavigationConfig
const { isNavigationReady: configReady } = useNavigationConfig();
const isNavigationReady = computed(() => configReady() && navigationOrder.value.length > 0);

// Async navigation state
const currentPath = ref<Record<string, string | null>>({});

// Watch route params and update data asynchronously
watchEffect(() => {
    const params = props.routeParams;
    try {
        currentPath.value = parseRouteToPath(params);

        // Trigger priority loading: navigation dropdowns first
        if (isNavigationReady.value) {
            loadNavigationWithPriority(currentPath.value);
        }
    } catch (error) {
        console.error("Error parsing route to path:", error);
        currentPath.value = {};
    }
});

// Methods
function handleToggleDropdown(type: string) {
    // Always toggle the dropdown first for immediate visual feedback
    toggleDropdown(type);

    // Only proceed with loading if dropdown is now open
    if (!isOpen(type)) {
        return;
    }

    // Check if data is already loaded - if so, no need to load
    if (getItems(type).length > 0) {
        return;
    }

    // Check if currently loading - if so, let it finish
    if (isLoading(type)) {
        return;
    }

    // Build filters from previous levels in the navigation hierarchy
    const order = navigationOrder.value;
    const typeIndex = order.findIndex((orderType: string) => orderType === type);
    const filters: Record<string, string> = {};

    // Add filters for all previous levels that have been selected
    for (let i = 0; i < typeIndex; i++) {
        const filterType = order[i];
        const filterValue = currentPath.value[filterType];
        if (filterValue) {
            filters[filterType] = filterValue;
        }
    }

    // Load data with appropriate filters (only if really needed)
    loadDropdownData(type, filters);
}

async function handleNavigate(type: string, value: string) {
    const newPath = buildNavigationUrl(currentPath.value, type, value);
    await navigateTo(newPath);
    closeAllDropdowns();

    // Load filtered data for the next level
    const order = navigationOrder.value;
    const typeIndex = order.findIndex((orderType: string) => orderType === type);
    if (typeIndex !== -1 && typeIndex < order.length - 1) {
        const nextType = order[typeIndex + 1];

        // Build filters up to this level
        const filters: Record<string, string> = {};
        for (let i = 0; i <= typeIndex; i++) {
            const filterType = order[i];
            const filterValue = filterType === type ? value : currentPath.value[filterType];
            if (filterValue) {
                filters[filterType] = filterValue;
            }
        }

        // Clear dependent dropdowns first to show filtered results
        clearDependentDropdowns(type);
        loadDropdownData(nextType, filters, true); // Force reload with new filters
    }
}

async function handleClearSelection(type: string) {
    const newPath = clearNavigationFrom(currentPath.value, type);
    await navigateTo(newPath);
    closeAllDropdowns();

    // Clear dependent dropdowns and reload unfiltered data
    clearDependentDropdowns(type);

    // Reload data for the next level with updated filters
    const typeIndex = navigationOrder.value.findIndex((orderType) => orderType === type);
    if (typeIndex !== -1 && typeIndex < navigationOrder.value.length - 1) {
        const nextType = navigationOrder.value[typeIndex + 1];

        // Build filters up to the previous level (excluding the cleared level)
        const filters: Record<string, string> = {};
        for (let i = 0; i < typeIndex; i++) {
            const filterType = navigationOrder.value[i];
            const filterValue = currentPath.value[filterType];
            if (filterValue) {
                filters[filterType] = filterValue;
            }
        }

        loadDropdownData(nextType, filters, true); // Force reload with updated filters
    }
}

// Click outside handler
const handleClickOutside = (event: Event): void => {
    const target = event.target as HTMLElement;
    if (!target.closest(".dropdown-container")) {
        closeAllDropdowns();
    }
};

// Auto-load first level data on mount
onMounted(async () => {
    try {
        // Initialize navigation configuration first
        await initializeNavigation();

        // Wait a bit to ensure the configuration is fully loaded
        await new Promise((resolve) => setTimeout(resolve, 100));

        // Add click outside handler
        document.addEventListener("click", handleClickOutside);
    } catch (error) {
        console.error("Failed to initialize navigation:", error);
    }
});

onUnmounted(() => {
    document.removeEventListener("click", handleClickOutside);
});

// Watch for navigation to become ready - no need to manually load first level
// since useNavigationState now handles proactive loading
watchEffect(() => {
    if (isNavigationReady.value && navigationOrder.value.length > 0) {
        // Navigation is ready - trigger context-aware preloading
        proactivelyLoadDropdownData(currentPath.value);
    }
});

// Watch for changes in navigation path and auto-load dependent data
watchEffect(() => {
    navigationOrder.value.forEach((type, index) => {
        if (index === 0) return; // Skip first level - already loaded on mount

        // Check if all previous levels are selected
        const previousLevelsSelected = navigationOrder.value
            .slice(0, index)
            .every((prevType) => currentPath.value[prevType]);

        if (previousLevelsSelected && currentPath.value[type]) {
            // Build filters for this level
            const filters: Record<string, string> = {};
            navigationOrder.value.slice(0, index).forEach((prevType) => {
                if (currentPath.value[prevType]) {
                    filters[prevType] = currentPath.value[prevType]!;
                }
            });

            // Load data if not already loaded
            if (getItems(type).length === 0 && !isLoading(type)) {
                loadDropdownData(type, filters);
            }
        }
    });
});
</script>
