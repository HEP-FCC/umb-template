/**
 * Global Search Control Composable
 * Provides a way to control search functionality from anywhere in the app
 */


interface SearchController {
    forceRefresh: () => Promise<void>;
    clearSearchAndRefresh: () => Promise<void>;
}

// Global state
const globalSearchController = ref<SearchController | null>(null);

export function useGlobalSearchControl() {
    const registerSearchController = (controller: SearchController) => {
        globalSearchController.value = controller;
    };

    const unregisterSearchController = () => {
        globalSearchController.value = null;
    };

    const forceRefresh = async () => {
        if (globalSearchController.value) {
            await globalSearchController.value.forceRefresh();
        }
    };

    const clearSearchAndRefresh = async () => {
        if (globalSearchController.value) {
            await globalSearchController.value.clearSearchAndRefresh();
        }
    };

    const hasController = computed(() => !!globalSearchController.value);

    return {
        registerSearchController,
        unregisterSearchController,
        forceRefresh,
        clearSearchAndRefresh,
        hasController,
    };
}
