<template>
    <div
        class="flex text-white flex-wrap items-center justify-between gap-4 rounded-lg border border-deep-blue-200 p-3 bg-deep-blue-900"
    >
        <!-- Entity Controls -->
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
            <!-- Selection controls -->
            <div class="flex items-center gap-2">
                <UCheckbox
                    :model-value="allEntitiesSelected"
                    :disabled="entities.length === 0"
                    @change="$emit('toggleSelectAll')"
                />
                <label class="text-sm font-medium cursor-pointer" @click="$emit('toggleSelectAll')">Select All</label>

                <!-- Selection counter -->
                <span
                    v-if="selectedCount > 0"
                    class="text-xs text-deep-blue-950 bg-deep-blue-100 px-2 py-1 rounded-full"
                >
                    {{ selectedCount }} selected
                </span>
            </div>

            <!-- Actions Dropdown -->
            <UDropdownMenu :items="actionItems" :ui="{ content: 'w-72' }">
                <UButton icon="i-heroicons-squares-2x2" color="neutral" variant="outline" size="sm" class="gap-2">
                    Actions
                    <UIcon name="i-heroicons-chevron-down" class="w-4 h-4 ml-1" />
                </UButton>
            </UDropdownMenu>

            <div class="h-6 w-px bg-deep-blue-400" />

            <UButton
                :icon="allMetadataExpanded ? 'i-heroicons-eye-slash' : 'i-heroicons-eye'"
                color="neutral"
                variant="outline"
                size="sm"
                class="cursor-pointer"
                @click="$emit('toggleAllMetadata')"
            >
                {{ allMetadataExpanded ? "All Metadata" : "All Metadata" }}
            </UButton>

            <!-- Metadata Tags Dropdown -->
            <MetadataTagsDropdown :entities="entities" />

            <div class="h-6 w-px bg-deep-blue-400" />

            <!-- Sorting controls -->
            <div class="flex items-center gap-2">
                <span class="text-sm font-medium">Sort by:</span>
                <USelectMenu
                    ref="sortSelectMenu"
                    :model-value="sortBy"
                    :items="sortingFieldOptions"
                    :loading="sortLoading"
                    placeholder="Select field"
                    value-key="value"
                    :search-input="{ placeholder: 'Search fields...' }"
                    :ui="{
                        content: 'max-w-xs overflow-hidden',
                    }"
                    size="sm"
                    class="w-38"
                    @update:model-value="$emit('updateSortBy', $event)"
                />
                <UButton
                    :icon="sortOrder === 'asc' ? 'i-heroicons-bars-arrow-up' : 'i-heroicons-bars-arrow-down'"
                    color="neutral"
                    variant="outline"
                    size="sm"
                    class="cursor-pointer"
                    @click="$emit('toggleSortOrder')"
                />
            </div>
        </div>

        <!-- Results Summary -->
        <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <!-- Left side: Results count and page size control -->
            <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
                <!-- Results count -->
                <div class="text-sm">
                    Showing
                    <strong> {{ displayRange.start }}-{{ displayRange.end }} </strong>
                    of
                    <strong>
                        {{ displayRange.total }}
                    </strong>
                </div>

                <div class="h-6 w-px bg-deep-blue-400" />

                <!-- Page size control -->
                <div class="flex items-center gap-1 text-sm">
                    <UTooltip
                        text="Number of items to load per page. Range: 25-1000. Press Enter to apply, Tab to navigate to results."
                        placement="top"
                    >
                        <span>Page size:</span>
                    </UTooltip>
                    <UInput
                        :model-value="pageSize"
                        type="number"
                        min="25"
                        max="1000"
                        size="sm"
                        class="w-16"
                        placeholder="25"
                        @update:model-value="handlePageSizeInput"
                        @blur="handlePageSizeBlur"
                        @keydown="handlePageSizeKeydown"
                    />
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import type { Entity } from "~/types/entity";
import MetadataTagsDropdown from "./MetadataTagsDropdown.vue";

// Composables
const { isAuthenticated } = useAuth();

interface Props {
    entities: Entity[];
    allEntitiesSelected: boolean;
    selectedCount: number;
    isDownloading: boolean;
    isDownloadingFiltered: boolean;
    allMetadataExpanded: boolean;
    sortBy: string;
    sortOrder: "asc" | "desc";
    sortingFieldOptions: Array<{ label: string; value: string }>;
    sortLoading: boolean;
    displayRange: { start: number; end: number; total: number };
    pageSize: number;
}

interface Emits {
    (
        e:
            | "toggleSelectAll"
            | "downloadSelected"
            | "downloadFiltered"
            | "deleteSelected"
            | "deleteFiltered"
            | "toggleAllMetadata"
            | "toggleSortOrder"
            | "handlePageSizeChange",
    ): void;
    (e: "updateSortBy", value: string): void;
    (e: "updatePageSize", value: number): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Ref for sort select menu
const sortSelectMenu = ref();

// Handle page size input to prevent unwanted "0" insertion
const handlePageSizeInput = (value: string | number) => {
    const numValue = typeof value === "string" ? parseInt(value, 10) : value;

    // Only emit if we have a valid number
    if (!isNaN(numValue) && numValue > 0) {
        emit("updatePageSize", numValue);
    }
};

// Handle page size keydown to prevent search refresh on tab navigation
const handlePageSizeKeydown = (event: KeyboardEvent) => {
    // If user presses Tab, ensure we don't trigger a search refresh
    if (event.key === "Tab") {
        // Allow the tab to proceed naturally without triggering page size change
        return;
    }

    // If user presses Enter, apply the current value and trigger page size change
    if (event.key === "Enter") {
        const target = event.target as HTMLInputElement;
        const value = parseInt(target.value, 10);

        if (!isNaN(value) && value >= 25) {
            const clampedValue = Math.max(25, Math.min(1000, value));
            target.value = clampedValue.toString();
            emit("updatePageSize", clampedValue);
            emit("handlePageSizeChange");
            target.blur(); // Remove focus after Enter
        }
        event.preventDefault();
    }
};

// Handle page size blur to ensure we have a valid value
const handlePageSizeBlur = (event: Event) => {
    const target = event.target as HTMLInputElement;
    const value = parseInt(target.value, 10);

    // If the input is empty or invalid, reset to current pageSize
    if (isNaN(value) || value < 25) {
        target.value = props.pageSize.toString();
    } else {
        // Clamp the value within bounds and apply it
        const clampedValue = Math.max(25, Math.min(1000, value));
        target.value = clampedValue.toString();

        // Only trigger page size change if the value actually changed
        if (clampedValue !== props.pageSize) {
            emit("updatePageSize", clampedValue);
            emit("handlePageSizeChange");
        }
    }
};

// Helper functions for delete confirmations
const handleDeleteSelected = () => {
    if (props.selectedCount === 0) return;

    const confirmed = window.confirm(
        `Are you sure you want to delete ${props.selectedCount} selected ${
            props.selectedCount === 1 ? "entity" : "entities"
        }?\n\nThis action cannot be undone.`,
    );

    if (confirmed) {
        emit("deleteSelected");
    }
};

const handleDeleteFiltered = () => {
    if (props.displayRange.total === 0) return;

    const confirmed = window.confirm(
        `⚠️ WARNING: You are about to delete ALL ${props.displayRange.total} filtered ${
            props.displayRange.total === 1 ? "entity" : "entities"
        }.\n\nThis will permanently delete all entities that match your current search filters.\n\nThis action cannot be undone.\n\nAre you absolutely sure you want to continue?`,
    );

    if (confirmed) {
        emit("deleteFiltered");
    }
};

// Clean action items with proper UX design
const actionItems = computed(() => [
    [
        {
            label: `Download Selected${props.selectedCount > 0 ? ` (${props.selectedCount})` : ""}`,
            icon: "i-heroicons-arrow-down-tray",
            disabled: props.selectedCount === 0 || props.isDownloading,
            class: "hover:bg-green-50 ",
            onSelect: () => emit("downloadSelected"),
        },
        {
            label: `Download All Filtered${props.displayRange.total > 0 ? ` (${props.displayRange.total})` : ""}`,
            icon: "i-heroicons-arrow-down-tray",
            disabled: props.displayRange.total === 0 || props.isDownloadingFiltered,
            class: "hover:bg-green-50 ",
            onSelect: () => emit("downloadFiltered"),
        },
    ],
    [
        {
            label: `Delete Selected${props.selectedCount > 0 ? ` (${props.selectedCount})` : ""}`,
            icon: "i-heroicons-trash",
            disabled: props.selectedCount === 0 || !isAuthenticated.value || props.isDownloading,
            class: "hover:bg-earth-50 ",
            onSelect: handleDeleteSelected,
        },
        {
            label: `Delete All Filtered${props.displayRange.total > 0 ? ` (${props.displayRange.total})` : ""}`,
            icon: "i-heroicons-trash",
            disabled: props.displayRange.total === 0 || !isAuthenticated.value || props.isDownloadingFiltered,
            class: "hover:bg-earth-50 ",
            onSelect: handleDeleteFiltered,
        },
    ],
]);
</script>
