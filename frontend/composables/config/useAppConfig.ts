/**
 * Dynamic App Configuration Composable
 *
 * Fetches and provides dynamic application configuration from the backend
 * /schema endpoint, allowing the frontend to adapt to different schemas
 * and configurations without hardcoding entity names or app titles.
 */

// Auto-imported: ref, computed, readonly

interface AppConfig {
    appTitle?: string;
    searchPlaceholder?: string;
    mainTable?: string;
    mainTableDisplayName?: string;
}

const appConfig = ref<AppConfig>({});
const isLoaded = ref(false);
const isLoading = ref(false);

export const useAppConfiguration = () => {
    const { baseUrl } = useApiClient();

    // Check API availability
    const apiAvailable = computed(() => !!baseUrl);

    /**
     * Format table name for display (e.g., "books" -> "Books")
     */
    const formatTableNameForDisplay = (tableName: string): string => {
        if (!tableName) return "Items";

        // Capitalize first letter and ensure it's plural
        let displayName = tableName.charAt(0).toUpperCase() + tableName.slice(1);
        if (!displayName.endsWith("s")) {
            displayName += "s";
        }

        return displayName;
    };

    /**
     * Load app configuration from backend
     */
    const loadAppConfig = async (): Promise<void> => {
        if (isLoading.value || isLoaded.value || !apiAvailable.value) {
            return;
        }

        isLoading.value = true;
        try {
            const { getSchema } = useSchema();
            const schemaResponse = await getSchema();
            const { appTitle, searchPlaceholder, main_table } = schemaResponse;

            appConfig.value = {
                appTitle: (appTitle as string) || "Metadata Browser",
                searchPlaceholder: (searchPlaceholder as string) || "Search...",
                mainTable: (main_table as string) || "entities",
                mainTableDisplayName: formatTableNameForDisplay((main_table as string) || "entities"),
            };

            isLoaded.value = true;
        } catch (error) {
            console.error("Failed to load app configuration:", error);
            // Fallback to defaults
            appConfig.value = {
                appTitle: "Metadata Browser",
                searchPlaceholder: "Search...",
                mainTable: "entities",
                mainTableDisplayName: "Entities",
            };
            isLoaded.value = true;
        } finally {
            isLoading.value = false;
        }
    };

    /**
     * Computed properties for easy access
     */
    const appTitle = computed(() => appConfig.value.appTitle || "Metadata Browser");
    const searchPlaceholder = computed(() => appConfig.value.searchPlaceholder || "Search...");
    const mainTable = computed(() => appConfig.value.mainTable || "entities");
    const mainTableDisplayName = computed(() => appConfig.value.mainTableDisplayName || "Entities");

    const defaultDescription = computed(() => `Explore and search through ${mainTableDisplayName.value.toLowerCase()}`);

    const searchDescription = computed(() => (filters?: Record<string, string>) => {
        if (filters && Object.keys(filters).length > 0) {
            const filterDesc = Object.entries(filters)
                .map(([key, value]) => `${key.replace("_", " ")}: ${value}`)
                .join(", ");
            return `Browse ${mainTableDisplayName.value.toLowerCase()} filtered by ${filterDesc}`;
        }
        return defaultDescription.value;
    });

    return {
        // State
        appConfig: readonly(appConfig),
        isLoaded: readonly(isLoaded),
        isLoading: readonly(isLoading),

        // Actions
        loadAppConfig,

        // Computed getters
        appTitle,
        searchPlaceholder,
        mainTable,
        mainTableDisplayName,
        defaultDescription,
        searchDescription,

        // Utilities
        formatTableNameForDisplay,
    };
};
