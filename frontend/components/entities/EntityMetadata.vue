<template>
    <div
        v-memo="[props.entityId, Object.keys(props.metadata).length, editState?.isEditing, lockStatesForTemplate]"
        class="rounded border-t bg-white"
        style="border-color: var(--theme-light-border-primary)"
    >
        <!-- Editing Mode -->
        <div v-if="editState?.isEditing" class="p-6">
            <div class="flex items-center justify-between mb-4">
                <div>
                    <h4 class="text-lg font-semibold">Edit Metadata</h4>
                    <p class="text-sm mt-1">
                        Modify the JSON metadata for this {{ mainTableDisplayName.toLowerCase().slice(0, -1) }}
                    </p>
                </div>
                <div class="flex gap-2">
                    <UButton
                        variant="solid"
                        size="sm"
                        :class="[
                            'text-white cursor-pointer bg-eco-600 hover:bg-eco-700 border-eco-600 hover:border-eco-700',
                        ]"
                        :disabled="!isAuthenticated || props.editState?.isSaving"
                        @click="saveMetadata"
                    >
                        <template #leading>
                            <UIcon
                                v-if="props.editState?.isSaving"
                                name="i-heroicons-arrow-path-20-solid"
                                class="animate-spin"
                            />
                            <UIcon v-else name="i-heroicons-check" />
                        </template>
                        {{
                            props.editState?.isSaving
                                ? "Saving..."
                                : isAuthenticated
                                ? "Save changes"
                                : "Login required"
                        }}
                    </UButton>
                    <UButton
                        icon="i-heroicons-x-mark"
                        class="text-neutral-600 cursor-pointer bg-neutral-100 hover:bg-neutral-200 border-neutral-300"
                        variant="outline"
                        size="sm"
                        @click="cancelEdit"
                    >
                        Cancel
                    </UButton>
                </div>
            </div>

            <div class="bg-space-50 rounded-lg p-4">
                <UTextarea
                    v-model="localEditJson"
                    :rows="getTextareaRows()"
                    placeholder="Edit metadata JSON..."
                    resize
                    class="font-mono text-sm w-full"
                    autofocus
                />
                <div class="flex items-center justify-between mt-3 text-xs">
                    <span>{{ getJsonStats(localEditJson) }}</span>
                    <div class="flex items-center gap-2">
                        <UButton
                            icon="i-heroicons-arrow-path"
                            class="text-neutral-500 cursor-pointer hover:text-neutral-700 hover:bg-neutral-100"
                            variant="ghost"
                            size="xs"
                            @click="formatJson"
                        >
                            Format JSON
                        </UButton>
                        <UButton
                            icon="i-heroicons-clipboard"
                            class="text-neutral-500 cursor-pointer hover:text-neutral-700 hover:bg-neutral-100"
                            variant="ghost"
                            size="xs"
                            @click="copyToClipboard(localEditJson)"
                        >
                            Copy
                        </UButton>
                    </div>
                </div>
            </div>
        </div>

        <!-- Display Mode -->
        <div v-else>
            <!-- Header -->
            <div
                class="flex items-center justify-between px-2 py-1 border-neutral-200"
                style="border-color: var(--theme-light-border-primary)"
            >
                <div class="flex items-center gap-4">
                    <h4 class="text-xs font-medium">Metadata ({{ visibleFieldCount }} fields)</h4>
                    <span v-if="entity.created_at" class="text-xs">
                        Created: {{ formatTimestamp(entity.created_at) }}
                    </span>
                </div>
                <div class="flex items-center gap-2">
                    <!-- UUID display (clickable to copy) -->
                    <UTooltip
                        v-if="props.entity.uuid"
                        text="Click to copy UUID to clipboard"
                        :popper="{ placement: 'top' }"
                    >
                        <!-- Desktop: Show full UUID -->
                        <div
                            class="hidden sm:flex items-center gap-1 px-2 py-1 rounded text-xs font-mono text-neutral-600 bg-neutral-50 hover:bg-neutral-100 cursor-pointer transition-colors border border-neutral-200"
                            @click="copyUuidToClipboard"
                        >
                            <UIcon name="i-heroicons-clipboard-document" class="w-3 h-3" />
                            <span class="select-none">{{ props.entity.uuid }}</span>
                        </div>

                        <!-- Mobile: Show just copy button -->
                        <UButton
                            icon="i-heroicons-clipboard-document"
                            class="sm:hidden text-neutral-600 cursor-pointer hover:text-neutral-800 hover:bg-neutral-100"
                            variant="ghost"
                            size="xs"
                            @click="copyUuidToClipboard"
                        >
                            UUID
                        </UButton>
                    </UTooltip>

                    <!-- Edit button -->
                    <UButton
                        icon="i-heroicons-pencil"
                        class="text-neutral-600 cursor-pointer hover:text-neutral-800 hover:bg-neutral-100"
                        variant="ghost"
                        size="xs"
                        :disabled="!isAuthenticated || actualEntityId <= 0"
                        @click="enterEditMode"
                    >
                        {{ actualEntityId <= 0 ? "Invalid Entity" : "Edit" }}
                    </UButton>
                </div>
            </div>
            <!-- Compact Content -->
            <div class="px-2">
                <!-- Unified Fields Grid Layout -->
                <div v-if="getAllFieldsComputed.length > 0" class="py-2">
                    <!-- Mobile layout: Single grid that expands each field to full width -->
                    <div class="block lg:hidden">
                        <div class="grid grid-cols-1 gap-2 text-xs">
                            <template v-for="field in getAllFieldsComputed" :key="field.key">
                                <!-- Mobile Field Card - Full width, scalable height -->
                                <div
                                    :class="getUnifiedFieldColorClass()"
                                    :style="getUnifiedFieldStyle(field)"
                                    class="group relative overflow-hidden rounded border transition-colors duration-200 shadow-sm"
                                >
                                    <!-- Background gradient (only for regular fields) -->
                                    <div
                                        v-if="field.category === 'regular'"
                                        class="absolute inset-0 opacity-5 group-hover:opacity-10 transition-opacity duration-200"
                                        :style="getUnifiedGradientStyle(field)"
                                    />

                                    <!-- Unified Field Header -->
                                    <div
                                        class="relative flex items-center justify-between px-2 py-1 border-b border-opacity-20"
                                        :style="[getUnifiedBorderStyle(field), getUnifiedFieldStyle(field, true)]"
                                    >
                                        <div class="flex items-center gap-1.5 flex-1 min-w-0">
                                            <!-- Unified icon (same as desktop) -->
                                            <div
                                                :class="getUnifiedIconContainerClass(field)"
                                                :style="getUnifiedIconStyle(field)"
                                            >
                                                <span class="text-[11px]">
                                                    {{ getUnifiedFieldIcon(field) }}
                                                </span>
                                            </div>
                                            <div class="font-medium text-xs truncate">
                                                {{ field.displayName }}
                                            </div>
                                        </div>

                                        <!-- Action buttons -->
                                        <div class="flex items-center gap-1 shrink-0">
                                            <!-- Lock indicator -->
                                            <UTooltip
                                                :text="
                                                    isFieldLocked(field.key)
                                                        ? `Field '${field.key}' is locked`
                                                        : `Field '${field.key}' is unlocked`
                                                "
                                            >
                                                <UButton
                                                    :icon="
                                                        isFieldLocked(field.key)
                                                            ? 'i-heroicons-lock-closed'
                                                            : 'i-heroicons-lock-open'
                                                    "
                                                    color="primary"
                                                    class="cursor-pointer"
                                                    variant="ghost"
                                                    size="xs"
                                                    :loading="pendingLockChanges.has(field.key)"
                                                    :disabled="!isAuthenticated"
                                                    @click="toggleFieldLock(field.key)"
                                                />
                                            </UTooltip>

                                            <!-- Copy button -->
                                            <UTooltip text="Copy field value">
                                                <UButton
                                                    icon="i-heroicons-clipboard"
                                                    class="cursor-pointer"
                                                    color="neutral"
                                                    variant="ghost"
                                                    size="xs"
                                                    @click="copyFieldValue(field.key, field.value)"
                                                />
                                            </UTooltip>
                                        </div>
                                    </div>

                                    <!-- Field Content - Mobile: scalable height, no truncation -->
                                    <div class="relative px-2 py-1.5 min-h-[1.5rem]">
                                        <div
                                            class="text-xs leading-tight break-words"
                                            :title="getUnifiedFieldValueTitle(field)"
                                        >
                                            {{ getUnifiedDisplayValue(field) }}
                                        </div>
                                    </div>
                                </div>
                            </template>
                        </div>
                    </div>

                    <!-- Desktop layout: Continuous grid flow without grouping -->
                    <div class="hidden lg:block">
                        <!-- Single continuous grid for all fields -->
                        <div class="grid grid-cols-12 gap-2 text-xs">
                            <template v-for="field in getAllFieldsComputed" :key="field.key">
                                <!-- Unified Field Card -->
                                <div
                                    :class="[getUnifiedGridSpanClass(field), getUnifiedFieldColorClass()]"
                                    :style="getUnifiedFieldStyle(field)"
                                    class="group relative overflow-hidden rounded border transition-colors duration-200 shadow-sm"
                                >
                                    <div
                                        v-if="field.category === 'regular'"
                                        class="absolute inset-0 opacity-5 group-hover:opacity-10 transition-opacity duration-200"
                                        :style="getUnifiedGradientStyle(field)"
                                    />

                                    <!-- Unified Field Header -->
                                    <div
                                        class="relative flex items-center justify-between px-2 py-1 border-b border-opacity-20"
                                        :style="[getUnifiedBorderStyle(field), getUnifiedFieldStyle(field, true)]"
                                    >
                                        <div class="flex items-center gap-1.5 flex-1 min-w-0">
                                            <!-- Unified icon -->
                                            <div
                                                :class="getUnifiedIconContainerClass(field)"
                                                :style="getUnifiedIconStyle(field)"
                                            >
                                                <span class="text-[11px]">
                                                    {{ getUnifiedFieldIcon(field) }}
                                                </span>
                                            </div>
                                            <!-- Field title -->
                                            <span class="font-medium text-xs truncate" :title="field.displayName">
                                                {{ field.displayName }}
                                            </span>
                                        </div>

                                        <div class="flex items-center gap-1 shrink-0">
                                            <!-- Lock indicator -->
                                            <UTooltip
                                                :text="
                                                    pendingLockChanges.has(field.key)
                                                        ? 'Updating lock state...'
                                                        : isFieldLocked(field.key)
                                                        ? `Unlock ${field.displayName}`
                                                        : `Lock ${field.displayName}`
                                                "
                                                :popper="{ placement: 'top' }"
                                            >
                                                <UButton
                                                    :icon="
                                                        pendingLockChanges.has(field.key)
                                                            ? 'i-heroicons-arrow-path'
                                                            : isFieldLocked(field.key)
                                                            ? 'i-heroicons-lock-closed'
                                                            : 'i-heroicons-lock-open'
                                                    "
                                                    color="primary"
                                                    variant="ghost"
                                                    size="xs"
                                                    :padded="false"
                                                    :disabled="!isAuthenticated || pendingLockChanges.has(field.key)"
                                                    :class="[
                                                        'w-4 h-4 p-0.5 transition-all duration-200',
                                                        {
                                                            'cursor-pointer opacity-70 hover:opacity-100 hover:bg-gray-100 rounded':
                                                                isAuthenticated && !pendingLockChanges.has(field.key),
                                                            'animate-spin': pendingLockChanges.has(field.key),
                                                            'cursor-not-allowed': !isAuthenticated,
                                                        },
                                                    ]"
                                                    @click="toggleFieldLock(field.key)"
                                                />
                                            </UTooltip>

                                            <!-- Special badges/indicators - using :color for dynamic behavior -->
                                            <UBadge
                                                v-if="field.type === 'vector'"
                                                color="primary"
                                                variant="soft"
                                                size="sm"
                                                class="shrink-0"
                                            >
                                                {{ (field.value as unknown[]).length }}
                                            </UBadge>
                                        </div>
                                    </div>

                                    <!-- Unified Field Value -->
                                    <div class="relative px-2 py-1.5 flex items-center justify-between min-h-[1.5rem]">
                                        <div
                                            :class="getUnifiedValueDisplayClass(field)"
                                            class="flex-1 text-xs leading-tight min-w-0 mr-2"
                                            :title="getUnifiedFieldValueTitle(field)"
                                        >
                                            {{ getUnifiedDisplayValue(field) }}
                                        </div>

                                        <!-- Action buttons -->
                                        <div class="flex items-center gap-1 shrink-0">
                                            <!-- Copy button - using Tailwind classes -->
                                            <UTooltip
                                                :text="`Copy ${field.displayName} value`"
                                                :popper="{ placement: 'top' }"
                                            >
                                                <UButton
                                                    icon="i-heroicons-clipboard-document"
                                                    :class="[
                                                        'w-4 h-4 p-0.5 rounded text-neutral-500 hover:text-info-600 hover:bg-gray-100 cursor-pointer opacity-70 hover:opacity-100 transition-all duration-200',
                                                    ]"
                                                    variant="ghost"
                                                    size="xs"
                                                    :padded="false"
                                                    @click="copyFieldValue(field.key, field.value)"
                                                />
                                            </UTooltip>
                                        </div>
                                    </div>
                                </div>
                            </template>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import type { MetadataEditState, Entity } from "~/types/api";

interface Props {
    entityId?: number;
    metadata: Record<string, unknown>;
    editState?: MetadataEditState;
    entity: Entity;
}

interface Emits {
    (e: "enterEdit", entityId: number, metadata: Record<string, unknown>): void;
    (e: "cancelEdit" | "saveMetadata", entityId: number, editedJson?: string): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Use the entityId directly, but validate it
const actualEntityId = computed(() => {
    const id = props.entityId ?? -1;
    if (id <= 0) {
        console.warn("EntityMetadata received invalid entity ID:", id);
    }
    return id;
});

// Performance optimizations - applied universally to ALL entity metadata
// No longer using lazy loading - show all fields by default

// Composables
const { formatFieldName, formatSizeInGiB, copyToClipboard, isStatusField, getStatusBadgeColor, formatTimestamp } =
    useUtils();
const { isAuthenticated } = useAuth();
const { mainTableDisplayName } = useAppConfiguration();

// Dynamic color system using CSS custom properties
// Dark mode disabled for consistent mobile rendering

// Color system for metadata fields using CSS variables
// Local reactive state for editing
const localEditJson = ref(props.editState?.json || "");

// Local reactive state for lock overrides (immediate UI updates)
const localLockStates = ref<Record<string, boolean>>({});
const pendingLockChanges = ref<Set<string>>(new Set());

// Watch for changes to editState prop and update local state
watch(
    () => props.editState?.json,
    (newJson) => {
        if (newJson !== undefined) {
            localEditJson.value = newJson;
        }
    },
    { immediate: true },
);

// Watch for metadata changes and update edit JSON if in edit mode
watch(
    [() => props.metadata, () => localLockStates.value],
    () => {
        // Only update if we're currently in edit mode and localLockStates is initialized
        if (props.editState?.isEditing && localLockStates.value !== undefined) {
            const editableMetadata = getEditableMetadata();
            const newJson = JSON.stringify(editableMetadata, null, 2);
            localEditJson.value = newJson;
        }
    },
    { deep: true },
);

// Get filtered metadata without lock fields for editing
const getEditableMetadata = (): Record<string, unknown> => {
    const filtered: Record<string, unknown> = {};
    Object.entries(props.metadata).forEach(([key, value]) => {
        // Skip lock fields themselves
        if (isLockField(key)) {
            return;
        }

        // Skip fields that are currently locked
        if (isFieldLocked(key)) {
            return;
        }

        filtered[key] = value;
    });
    return filtered;
};

// Methods
const enterEditMode = (): void => {
    const editableMetadata = getEditableMetadata();
    emit("enterEdit", actualEntityId.value, editableMetadata);
};

const cancelEdit = (): void => {
    emit("cancelEdit", actualEntityId.value);
};

const saveMetadata = (): void => {
    emit("saveMetadata", actualEntityId.value, localEditJson.value);
};

const formatJson = (): void => {
    try {
        const parsed = JSON.parse(localEditJson.value);
        const formatted = JSON.stringify(parsed, null, 2);
        localEditJson.value = formatted;
    } catch (error) {
        console.error("Invalid JSON:", error);
        // Show user feedback for invalid JSON
        alert("Invalid JSON format. Please check your syntax.");
    }
};

// Lock-related functionality
const { updateMetadataLock } = useApiClient();
const toast = useToast();

// Use a simple reactive ref instead of computed for template reactivity
const lockStatesForTemplate = ref<Record<string, boolean>>({});

// Function to update the template state
const updateLockStatesForTemplate = () => {
    const lockStates: Record<string, boolean> = {};

    // Process local state first (most up-to-date)
    if (localLockStates.value) {
        Object.entries(localLockStates.value).forEach(([fieldName, isLocked]) => {
            lockStates[fieldName] = !!isLocked;
        });
    }

    // Process metadata lock fields as fallback
    Object.keys(props.metadata).forEach((key) => {
        if (key.includes("__lock__")) {
            const fieldName = key.replace("__", "").replace("__lock__", "");
            const isLocked = !!props.metadata[key];

            // Only add if not already in local state
            if (!localLockStates.value || !(fieldName in localLockStates.value)) {
                lockStates[fieldName] = isLocked;
                // Sync to local state
                if (localLockStates.value) {
                    localLockStates.value[fieldName] = isLocked;
                }
            }
        }
    });

    lockStatesForTemplate.value = lockStates;
};

// Watch for changes and update template state
watch([localLockStates, () => props.metadata], updateLockStatesForTemplate, { deep: true, immediate: true });

const isFieldLocked = (fieldName: string): boolean => {
    return !!lockStatesForTemplate.value[fieldName];
};
const toggleFieldLock = async (fieldName: string): Promise<void> => {
    if (!isAuthenticated.value || !actualEntityId.value) {
        toast.add({
            title: "Authentication Required",
            description: "Please login to manage field locks.",
            color: "warning",
        });
        return;
    }

    const currentlyLocked = isFieldLocked(fieldName);
    const newLockState = !currentlyLocked;

    try {
        // Mark this field as having a pending change (for loading state)
        pendingLockChanges.value.add(fieldName);

        // Make API call FIRST - wait for success before updating UI
        const response = await updateMetadataLock(actualEntityId.value, fieldName, newLockState);

        if (response.success) {
            // Only update local state AFTER successful API response
            localLockStates.value[fieldName] = newLockState;

            // Manually trigger template update
            updateLockStatesForTemplate();

            toast.add({
                title: "Success",
                description: `Field "${formatFieldName(fieldName)}" ${
                    newLockState ? "locked" : "unlocked"
                } successfully.`,
                color: "success",
            });

            // Clear the pending change
            pendingLockChanges.value.delete(fieldName);
        } else {
            console.error("Lock operation failed:", response);

            // Clear pending change and show error
            pendingLockChanges.value.delete(fieldName);

            toast.add({
                title: "Error",
                description: response.message || "Failed to update field lock.",
                color: "error",
            });
        }
    } catch (error) {
        console.error("Failed to toggle field lock:", error);

        // Clear pending change - error interceptor will handle user notification
        pendingLockChanges.value.delete(fieldName);

        // Re-throw so error interceptor can handle it
        throw error;
    }
};

const getJsonStats = (json: string): string => {
    const lines = json.split("\n").length;
    const chars = json.length;
    return `${lines} lines, ${chars} characters`;
};

const getTextareaRows = (): number => {
    const lineCount = localEditJson.value.split("\n").length;
    return Math.max(15, Math.min(lineCount + 2, 35));
};

const isSizeField = (key: string): boolean => {
    return key.toLowerCase() === "size";
};

const isVectorField = (value: unknown): boolean => {
    return (
        Array.isArray(value) &&
        value.length > 0 &&
        value.every((item) => ["number", "string", "boolean"].includes(typeof item))
    );
};

const isLongString = (value: unknown): boolean => {
    return typeof value === "string" && value.length > 50;
};

// Check if a string value is actually a number
const isNumericString = (value: unknown): boolean => {
    if (typeof value !== "string") return false;
    const trimmed = value.trim();
    if (trimmed === "") return false;

    // Check for various number formats
    const number = Number(trimmed);
    return !isNaN(number) && isFinite(number);
};

// Parse numeric string to actual number
const parseNumericString = (value: string): number => {
    return Number(value.trim());
};

// Get the actual value for display (convert numeric strings to numbers)
const getDisplayValue = (value: unknown): unknown => {
    if (isNumericString(value)) {
        return parseNumericString(value as string);
    }
    return value;
};

const formatShortValue = (value: unknown): string => {
    if (typeof value === "number") {
        return Number.isInteger(value) ? value.toString() : value.toFixed(3);
    }
    if (typeof value === "boolean") {
        return value ? "Yes" : "No";
    }
    // Don't truncate strings - display them in full
    return String(value);
};

const formatVectorPreview = (value: unknown[]): string => {
    const firstFive = value.slice(0, 5);
    const preview =
        firstFive
            .map((item) => {
                if (typeof item === "number") {
                    return Number.isInteger(item) ? item.toString() : item.toFixed(3);
                }
                return String(item);
            })
            .join(", ") + (value.length > 5 ? ", ..." : "");
    return preview;
};

const getTypeIcon = (type: string): string => {
    switch (type) {
        case "number":
            return "#";
        case "boolean":
            return "✓";
        case "vector":
            return "<>";
        case "longString":
            return "A";
        default: // shortString
            return "A";
    }
};

const getContentLength = (key: string, value: unknown, type: string): number => {
    const formattedKey = formatFieldName(key);
    let contentValue = "";

    switch (type) {
        case "vector":
            contentValue = formatVectorPreview(value as unknown[]);
            break;
        case "number": {
            const displayValue = getDisplayValue(value);
            contentValue = isSizeField(key) ? formatSizeInGiB(displayValue) : formatShortValue(displayValue);
            break;
        }
        default:
            contentValue = formatShortValue(value);
    }

    // Return total estimated character width
    return formattedKey.length + contentValue.length;
};

const getGridSpanClass = (key: string, value: unknown, type: string): string => {
    // Long strings always take full width
    if (type === "longString") {
        return "col-span-12";
    }

    const contentLength = getContentLength(key, value, type);

    // More compact grid spans based on content length and type (12-column grid)
    if (type === "number" || type === "boolean") {
        // Numbers and booleans are typically short - keep them very compact
        return contentLength <= 30 ? "col-span-2" : "col-span-3";
    } else if (type === "vector") {
        // Vectors need more space but be more aggressive with compacting
        return contentLength <= 30
            ? "col-span-3"
            : contentLength <= 50
            ? "col-span-4"
            : contentLength <= 70
            ? "col-span-6"
            : "col-span-12";
    } else {
        // Strings - be more aggressive with space
        if (contentLength <= 15) return "col-span-2";
        if (contentLength <= 40) return "col-span-2";
        if (contentLength <= 60) return "col-span-3";
        if (contentLength <= 80) return "col-span-4";
        return "col-span-12";
    }
};

const getFieldValueTitle = (key: string, value: unknown, type: string): string => {
    // Return full value for tooltip on truncated fields
    if (type === "vector") {
        const fullArray = value as unknown[];
        return fullArray
            .map((item) =>
                typeof item === "number" ? (Number.isInteger(item) ? item.toString() : item.toFixed(3)) : String(item),
            )
            .join(", ");
    }

    if (type === "number") {
        const displayValue = getDisplayValue(value);
        if (isSizeField(key)) {
            return formatSizeInGiB(displayValue);
        }
        return formatShortValue(displayValue);
    }

    return formatShortValue(value);
};

// Special fields handling (comments and descriptions)
const isSpecialField = (key: string): boolean => {
    const normalizedKey = key.toLowerCase();
    return (
        normalizedKey.includes("comment") ||
        normalizedKey.includes("description") ||
        normalizedKey.includes("desc") ||
        normalizedKey === "summary" ||
        normalizedKey === "note" ||
        normalizedKey === "notes"
    );
};

// Lock fields handling (internal metadata fields)
const isLockField = (key: string): boolean => {
    return key.includes("__lock__");
};

// Get count of visible fields (excluding lock fields) - optimized
const visibleFieldCount = computed(() => {
    return getAllFieldsComputed.value.length;
});

// UNIFIED FIELD PROCESSING - Simplified approach to reduce code duplication
// Define unified field interface
interface UnifiedField {
    key: string;
    value: unknown;
    displayName: string;
    category: "special" | "status" | "regular";
    type: string;
    priority: number; // For layout grouping
    color?: string; // For status fields
    style?: string;
}

// Unified field processing - combines all field types into a single structure
const getAllFieldsComputed = computed((): UnifiedField[] => {
    const fields: UnifiedField[] = [];
    const metadata = props.metadata;

    Object.entries(metadata).forEach(([key, value]) => {
        // Skip lock fields
        if (isLockField(key)) return;

        let field: UnifiedField;

        if (isSpecialField(key)) {
            field = {
                key,
                value,
                displayName: getSpecialFieldTitle(key),
                category: "special",
                type: "special",
                priority: 1, // Highest priority - renders first
            };
        } else if (isStatusField(key)) {
            field = {
                key,
                value,
                displayName: formatFieldName(key),
                category: "status",
                type: "status",
                priority: 1, // Same priority as special fields to appear in same row
                color: getStatusBadgeColor(value),
            };
        } else {
            // Regular field - determine type
            let type: string;
            if (isVectorField(value)) type = "vector";
            else if (typeof value === "number") type = "number";
            else if (typeof value === "boolean") type = "boolean";
            else if (isNumericString(value)) type = "number";
            else if (typeof value === "string" && isLongString(value)) type = "longString";
            else type = "shortString";

            // Set priority based on type for logical grouping
            let priority = 2;
            if (type === "number" || type === "boolean") priority = 2;
            else if (type === "shortString") priority = 3;
            else if (type === "vector") priority = 4;
            else if (type === "longString") priority = 5;

            field = {
                key,
                value,
                displayName: formatFieldName(key),
                category: "regular",
                type,
                priority,
            };
        }

        fields.push(field);
    });

    // Sort by priority, then by display name
    return fields.sort((a, b) => {
        if (a.priority !== b.priority) {
            return a.priority - b.priority;
        }
        return a.displayName.localeCompare(b.displayName);
    });
});

// UNIFIED STYLING FUNCTIONS - Preference for Tailwind classes over CSS variables

const getUnifiedIconContainerClass = (_field: UnifiedField): string => {
    return "flex-shrink-0 flex items-center justify-center w-4 h-4 rounded";
};

const getUnifiedGradientStyle = (field: UnifiedField): Record<string, string> => {
    const colors = getFieldColorsMemoized(field);
    return {
        background: `linear-gradient(to bottom right, ${colors.grad400}, ${colors.grad600})`,
    };
};

// Enhanced color scheme mapping based on field categories using CSS variables
const getSemanticColorForFieldType = (fieldType: string): string => {
    const typeMapping: Record<string, string> = {
        number: "gray",
        boolean: "success",
        vector: "accent",

        longString: "gray",
        shortString: "gray",

        special: "gray",
        status: "secondary",

        // Map the new custom status colors (using kebab-case to match @theme definitions)
        "status-completed": "status-completed",
        "status-in-progress": "status-in-progress",
        "status-failed": "status-failed",
        "status-active": "status-active",
        "status-neutral": "status-neutral",

        // Legacy fallbacks
        success: "status-completed",
        warning: "status-in-progress",
        error: "status-failed",
        info: "status-active",
        neutral: "status-neutral",
    };

    return typeMapping[fieldType] || "status-neutral";
};

// Generate CSS variable references for color schemes
const getCSSVariableForColor = (semantic: string, shade: string | number = "500") => {
    return `var(--color-${semantic}-${shade})`;
};

// CENTRALIZED COLOR RESOLUTION - Eliminates code duplication
const resolveFieldSemanticColor = (field: UnifiedField): string => {
    if (field.category === "status" && field.color) {
        return field.color;
    } else if (field.category === "special") {
        return "special";
    } else {
        return field.type;
    }
};

// Centralized color variables generator
const getFieldColorVariables = (field: UnifiedField) => {
    const semanticColor = getSemanticColorForFieldType(resolveFieldSemanticColor(field));
    return {
        bg50: getCSSVariableForColor(semanticColor, "50"),
        bg100: getCSSVariableForColor(semanticColor, "100"),
        bg300: getCSSVariableForColor(semanticColor, "300"),
        border200: getCSSVariableForColor(semanticColor, "200"),
        text300: getCSSVariableForColor(semanticColor, "300"),
        text600: getCSSVariableForColor(semanticColor, "600"),
        text700: getCSSVariableForColor(semanticColor, "700"),
        grad400: getCSSVariableForColor(semanticColor, "400"),
        grad600: getCSSVariableForColor(semanticColor, "600"),
        main: getCSSVariableForColor(semanticColor, "main"),
    };
};

// Memoization for color computation - ultimate optimization
const colorMemo = new Map<string, ReturnType<typeof getFieldColorVariables>>();
const getFieldColorsMemoized = (field: UnifiedField) => {
    const key = `${field.category}-${field.type}-${field.color || ""}`;
    if (!colorMemo.has(key)) {
        colorMemo.set(key, getFieldColorVariables(field));
    }
    return colorMemo.get(key)!;
};

// UNIFIED STYLING FUNCTIONS - CSS Variable-based dynamic color system

const getUnifiedFieldColorClass = (): string => {
    return "group relative overflow-hidden rounded border transition-colors duration-200 shadow-sm";
};

const getUnifiedFieldStyle = (field: UnifiedField, isHeader: boolean = false): Record<string, string> => {
    const colors = getFieldColorsMemoized(field);

    if (field.key === "path" || field.key === "comment" || field.key == "description") {
        return {
            backgroundColor: isHeader ? "#cad7fb" : "#eff2ff",
            borderColor: "#cad7fb",
            "--hover-bg-color": "#e8efff",
        };
    }

    return {
        backgroundColor: isHeader ? colors.bg300 : colors.bg50,
        borderColor: colors.border200,
        "--hover-bg-color": colors.bg100,
    };
};

const getUnifiedBorderStyle = (field: UnifiedField): Record<string, string> => {
    const colors = getFieldColorsMemoized(field);
    return {
        borderColor: colors.border200,
    };
};

const getUnifiedIconStyle = (field: UnifiedField): Record<string, string> => {
    const colors = getFieldColorsMemoized(field);
    return {
        backgroundColor: "var(--color-deep-blue-main)",
        color: colors.text300,
    };
};

const getUnifiedFieldIcon = (field: UnifiedField): string => {
    if (field.category === "special") {
        return getTypeIcon(field.type);
    } else if (field.category === "status") {
        return getTypeIcon(field.type);
    } else {
        return getTypeIcon(field.type);
    }
};

// Grid span calculation for unified fields - restored original desktop logic
const getUnifiedGridSpanClass = (field: UnifiedField): string => {
    // Return original desktop grid classes for the 12-column grid system
    if (field.category === "special") {
        return getSpecialFieldSpanClass(
            field.value,
            getAllFieldsComputed.value.filter((f) => f.category === "status").length,
        );
    } else if (field.category === "status") {
        return getStatusFieldSpanClass(field.value);
    } else {
        return getGridSpanClass(field.key, field.value, field.type);
    }
};

// Value display functions
const getUnifiedDisplayValue = (field: UnifiedField): string => {
    if (field.type === "vector") {
        return formatVectorPreview(field.value as unknown[]);
    } else if (field.type === "number") {
        const displayValue = getDisplayValue(field.value);
        return isSizeField(field.key) ? formatSizeInGiB(displayValue) : formatShortValue(displayValue);
    } else {
        return formatShortValue(field.value);
    }
};

const getUnifiedFieldValueTitle = (field: UnifiedField): string => {
    return getFieldValueTitle(field.key, field.value, field.type);
};

const getUnifiedValueDisplayClass = (field: UnifiedField): string => {
    const classes = [];

    if (field.type === "vector") {
        classes.push("font-mono text-xs");
    } else if (field.type === "shortString" || field.type === "longString") {
        classes.push("font-medium");
    }

    // Check if the value looks like a path (contains / or \)
    const value = String(field.value);
    const isPath = value.includes("/") || value.includes("\\");

    if (field.type === "longString" || isPath) {
        // Allow wrapping for long strings and paths
        classes.push("break-words");
    } else {
        // Truncate shorter strings
        classes.push("truncate");
    }

    return classes.join(" ");
};

const getSpecialFieldTitle = (key: string): string => {
    const normalizedKey = key.toLowerCase();
    if (normalizedKey.includes("description") || normalizedKey.includes("desc")) return "Description";
    if (normalizedKey.includes("comment")) return "Comment";
    return formatFieldName(key);
};

// Determine column span for special fields based on content length and status fields presence
const getSpecialFieldSpanClass = (value: unknown, statusFieldsCount: number): string => {
    const stringValue = String(value);
    const isLong = stringValue.length > 60; // Reduced threshold for more compact layout

    // If there are status fields, we need to reserve space for them
    if (statusFieldsCount > 0) {
        // Reserve less space for status fields (2 columns each, up to 3 status fields = 6 columns max)
        const statusColumnsReserved = Math.min(statusFieldsCount * 2, 6);
        const availableColumns = 12 - statusColumnsReserved;

        if (isLong) {
            // Long content takes all remaining space after status fields
            if (availableColumns >= 6) return "col-span-6";
            if (availableColumns >= 4) return "col-span-4";
            return "col-span-3";
        } else {
            // Short content takes most of remaining space
            if (availableColumns >= 8) return "col-span-5";
            if (availableColumns >= 6) return "col-span-4";
            if (availableColumns >= 4) return "col-span-3";
            return "col-span-3";
        }
    }

    // No status fields, use original logic
    return isLong ? "col-span-12" : "col-span-6";
};

// Copy field value to clipboard with type handling
const copyFieldValue = async (key: string, value: unknown): Promise<void> => {
    try {
        let textToCopy: string;

        // Handle different types of values
        if (Array.isArray(value)) {
            // For arrays, copy as JSON
            textToCopy = JSON.stringify(value, null, 2);
        } else if (typeof value === "object" && value !== null) {
            // For objects, copy as JSON
            textToCopy = JSON.stringify(value, null, 2);
        } else {
            // For primitives, copy as string
            textToCopy = String(value);
        }

        await copyToClipboard(textToCopy);

        // Show success toast
        const toast = useToast();
        toast.add({
            title: "Value copied to clipboard",
            icon: "i-heroicons-clipboard-document-check",
        });
    } catch (error) {
        console.error("Failed to copy field value:", error);

        // Show error toast
        const toast = useToast();
        toast.add({
            title: "Failed to copy value",
            description: "Please try again",
            icon: "i-heroicons-exclamation-triangle",
            color: "error",
        });
    }
};

// Copy UUID to clipboard
const copyUuidToClipboard = async (): Promise<void> => {
    if (!props.entity.uuid) return;

    try {
        await copyToClipboard(props.entity.uuid);

        // Show success toast
        const toast = useToast();
        toast.add({
            title: "UUID copied to clipboard",
            icon: "i-heroicons-clipboard-document-check",
        });
    } catch (error) {
        console.error("Failed to copy UUID:", error);

        // Show error toast
        const toast = useToast();
        toast.add({
            title: "Failed to copy UUID",
            description: "Please try again",
            icon: "i-heroicons-exclamation-triangle",
            color: "error",
        });
    }
};

// Status field styling functions - updated to use CSS variables
const getStatusFieldSpanClass = (value: unknown): string => {
    const stringValue = String(value);
    return stringValue.length > 20 ? "col-span-2" : "col-span-2";
};
</script>

<style scoped>
/* Component uses inline styles for dynamic colors via Vue's :style binding */
/* CSS custom properties are generated from the colors.ts configuration */

/* Enhanced hover transitions are now handled via global CSS */
.group {
    transition: background-color 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* Smooth transitions for color changes */
.transition-colors {
    transition-property: background-color, border-color, color;
    transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
    transition-duration: 200ms;
}
</style>
