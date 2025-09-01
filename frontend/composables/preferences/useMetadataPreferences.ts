/**
 * Metadata Preferences Management Composable
 *
 * Manages user preferences for which metadata fields should be displayed
 * as tags/badges on all entities. Preferences are stored in a secure,
 * never-expiring cookie for persistence across page refreshes and navigation.
 */

import { APP_CONFIG } from "~/config/app.config";

interface MetadataPreferences {
    selectedFields: string[];
    lastUpdated: number;
}

const COOKIE_NAME = `${APP_CONFIG.cookies.namePrefix}-metadata-preferences`;

// Global singleton state for metadata preferences
const globalSelectedFields = ref<string[]>([]);
const globalIsLoading = ref(false);
const globalError = ref<string | null>(null);
const isInitialized = ref(false);

/**
 * Composable for managing metadata display preferences
 */
export const useMetadataPreferences = () => {
    /**
     * Initialize preferences from cookie (only once)
     */
    const initializePreferences = () => {
        if (isInitialized.value) return;

        try {
            const preferenceCookie = useCookie<MetadataPreferences>(COOKIE_NAME, {
                default: () => ({
                    selectedFields: [...APP_CONFIG.metadata.defaultSelectedFields],
                    lastUpdated: Date.now(),
                }),
                secure: process.env.NODE_ENV === "production",
                sameSite: "strict",
                httpOnly: false, // Need client-side access for reactive updates
                maxAge: 60 * 60 * 24, // 1 day
            });

            if (preferenceCookie.value?.selectedFields) {
                globalSelectedFields.value = preferenceCookie.value.selectedFields;
            }
            isInitialized.value = true;
        } catch (err) {
            console.warn("Failed to load metadata preferences:", err);
            globalError.value = "Failed to load saved preferences";
            globalSelectedFields.value = [];
            isInitialized.value = true;
        }
    };

    /**
     * Save preferences to secure cookie
     */
    const savePreferences = () => {
        try {
            const preferences: MetadataPreferences = {
                selectedFields: globalSelectedFields.value,
                lastUpdated: Date.now(),
            };

            const preferenceCookie = useCookie<MetadataPreferences>(COOKIE_NAME, {
                default: () => ({ selectedFields: [], lastUpdated: Date.now() }),
                secure: process.env.NODE_ENV === "production",
                sameSite: "strict",
                httpOnly: false,
            });

            preferenceCookie.value = preferences;
            globalError.value = null;
        } catch (err) {
            console.error("Failed to save metadata preferences:", err);
            globalError.value = "Failed to save preferences";
        }
    };

    /**
     * Toggle a metadata field in the selected fields
     */
    const toggleField = (fieldName: string) => {
        const index = globalSelectedFields.value.indexOf(fieldName);
        if (index > -1) {
            globalSelectedFields.value.splice(index, 1);
        } else {
            globalSelectedFields.value.push(fieldName);
        }
        savePreferences();
    };

    /**
     * Add a field to selected fields
     */
    const addField = (fieldName: string) => {
        if (!globalSelectedFields.value.includes(fieldName)) {
            globalSelectedFields.value.push(fieldName);
            savePreferences();
        }
    };

    /**
     * Remove a field from selected fields
     */
    const removeField = (fieldName: string) => {
        const index = globalSelectedFields.value.indexOf(fieldName);
        if (index > -1) {
            globalSelectedFields.value.splice(index, 1);
            savePreferences();
        }
    };

    /**
     * Clear all selected fields
     */
    const clearAllFields = () => {
        globalSelectedFields.value = [];
        savePreferences();
    };

    /**
     * Set selected fields (replace all)
     */
    const setSelectedFields = (fields: string[]) => {
        globalSelectedFields.value = [...fields];
        savePreferences();
    };

    /**
     * Check if a field is selected
     */
    const isFieldSelected = (fieldName: string): boolean => {
        return globalSelectedFields.value.includes(fieldName);
    };

    /**
     * Get metadata badges for an entity based on selected preferences
     */
    const getMetadataBadges = (entity: {
        metadata?: Record<string, unknown>;
    }): Array<{
        key: string;
        label: string;
        value: string;
        color: "primary" | "neutral" | "success" | "warning" | "info" | "error";
    }> => {
        if (!entity.metadata || globalSelectedFields.value.length === 0) {
            return [];
        }

        return globalSelectedFields.value.map((fieldName: string) => {
            const value = entity.metadata?.[fieldName];
            const displayValue = value !== undefined && value !== null ? String(value) : "NONE";

            return {
                key: `metadata_${fieldName}`,
                label: formatFieldName(fieldName),
                value: displayValue,
                color: displayValue === "NONE" ? ("info" as const) : ("info" as const),
            };
        });
    };

    /**
     * Get all available metadata fields from a collection of entities - optimized
     */
    const getAvailableFields = (entities: Array<{ metadata?: Record<string, unknown> }>): string[] => {
        const fieldsSet = new Set<string>();

        entities.forEach((entity) => {
            if (entity.metadata) {
                // Use Object.keys for better performance than Object.entries when we only need keys
                Object.keys(entity.metadata).forEach((key) => {
                    // Exclude lock fields and other internal fields - optimized string checks
                    if (!key.includes("__lock__") && !key.startsWith("_")) {
                        fieldsSet.add(key);
                    }
                });
            }
        });

        return Array.from(fieldsSet).sort();
    };

    /**
     * Get metadata fields that are currently locked across entities - optimized
     */
    const getLockedFields = (entities: Array<{ metadata?: Record<string, unknown> }>): Set<string> => {
        const lockedFields = new Set<string>();

        entities.forEach((entity) => {
            if (entity.metadata) {
                Object.keys(entity.metadata).forEach((key) => {
                    if (key.includes("__lock__") && entity.metadata?.[key]) {
                        const fieldName = key.replace("__", "").replace("__lock__", "");
                        lockedFields.add(fieldName);
                    }
                });
            }
        });

        return lockedFields;
    };

    /**
     * Format field name for display
     */
    const formatFieldName = (fieldName: string): string => {
        return fieldName
            .split("_")
            .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" ");
    };

    // Initialize on composable creation
    if (!isInitialized.value) {
        initializePreferences();
    }

    return {
        // Reactive state
        selectedFields: readonly(globalSelectedFields),
        isLoading: readonly(globalIsLoading),
        error: readonly(globalError),

        // Actions
        toggleField,
        addField,
        removeField,
        clearAllFields,
        setSelectedFields,
        initializePreferences,

        // Getters
        isFieldSelected,
        getMetadataBadges,
        getAvailableFields,
        getLockedFields,
        formatFieldName,
    };
};
