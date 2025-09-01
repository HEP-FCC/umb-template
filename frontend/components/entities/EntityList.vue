<template>
    <div>
        <!-- Screen reader instructions for keyboard navigation -->
        <div class="sr-only">
            Entity list. Use Tab to navigate through items. Press Enter or Space to expand metadata, or S to toggle
            selection.
        </div>

        <!-- Entity List -->
        <div class="space-y-1.5" role="list" aria-label="Search results">
            <!-- Entity cards -->
            <UCard
                v-for="(entity, index) in entities"
                :key="getEntityId(entity)"
                :data-entity-card="index"
                :ui="{ body: 'sm:p-1.5' }"
                class="overflow-hidden select-text cursor-pointer root-p-0"
                role="listitem"
                tabindex="0"
                :aria-label="`Entity: ${entity.name}`"
                @click="handleRowClick($event, getEntityId(entity))"
                @keydown="handleEntityKeydown($event, getEntityId(entity))"
            >
                <div class="px-2">
                    <div class="flex items-center justify-between gap-3">
                        <div class="flex-1 min-w-0">
                            <!-- Row 1: Entity name (full width) -->
                            <div class="flex items-center gap-2 mb-0.5">
                                <UCheckbox
                                    :model-value="isEntitySelected(getEntityId(entity))"
                                    class="flex-shrink-0"
                                    tabindex="0"
                                    :aria-label="`Select entity: ${entity.name}`"
                                    @click.stop
                                    @change="toggleEntitySelection(getEntityId(entity))"
                                />
                                <h3 class="text-sm sm:text-base font-semibold truncate flex-1">
                                    {{ entity.name }}
                                </h3>
                            </div>

                            <!-- Row 2: Badges and timestamps in one compact row -->
                            <div class="flex items-center justify-between gap-2 ml-6">
                                <!-- Left side: Entity badges -->
                                <div class="flex flex-wrap gap-1.5 flex-1 min-w-0">
                                    <template v-for="badge in getEntityBadges(entity, activeFilters)" :key="badge.key">
                                        <UBadge
                                            v-if="badge.value"
                                            :color="badge.color"
                                            :variant="
                                                badge.key && String(badge.key).startsWith('status_') ? 'soft' : 'subtle'
                                            "
                                            size="sm"
                                        >
                                            {{ badge.label }}: {{ badge.value }}
                                        </UBadge>
                                    </template>
                                </div>

                                <!-- Right side: Timestamps -->
                                <div class="relative text-xs min-h-[16px] flex items-end flex-shrink-0 ml-2">
                                    <span v-if="entity.updated_at" class="text-right hidden md:inline">
                                        Updated: {{ formatTimestamp(entity.updated_at) }}
                                    </span>
                                    <!-- Show abbreviated timestamp on mobile/tablet -->
                                    <span v-if="entity.updated_at" class="text-right md:hidden text-xs">
                                        {{ formatTimestamp(entity.updated_at).split(" ").slice(0, 2).join(" ") }}
                                    </span>
                                    <span
                                        v-if="wasEntityEdited(entity)"
                                        class="absolute -top-4 right-0 text-earth-600 text-xs whitespace-nowrap"
                                        :title="getEditedTooltip(entity)"
                                    >
                                        Edited
                                    </span>
                                </div>
                            </div>
                        </div>

                        <UButton
                            :icon="
                                isMetadataExpanded(getEntityId(entity))
                                    ? 'i-heroicons-chevron-up'
                                    : 'i-heroicons-chevron-down'
                            "
                            color="neutral"
                            variant="ghost"
                            size="xs"
                            class="flex-shrink-0"
                            :aria-label="
                                isMetadataExpanded(getEntityId(entity))
                                    ? `Collapse metadata for ${entity.name}`
                                    : `Expand metadata for ${entity.name}`
                            "
                            @click.stop="toggleMetadata(getEntityId(entity))"
                        />
                    </div>
                </div>

                <!-- Metadata component (inline) -->
                <div v-if="isMetadataExpanded(getEntityId(entity))" class="bg-space-50 cursor-default my-1" @click.stop>
                    <EntityMetadata
                        :entity-id="getEntityId(entity)"
                        :entity="entity"
                        :metadata="entity.metadata || {}"
                        :edit-state="metadataEditState[getEntityId(entity)]"
                        @enter-edit="enterEditMode"
                        @cancel-edit="cancelEdit"
                        @save-metadata="saveMetadata"
                        @refresh-entity="refreshEntity"
                    />
                </div>
            </UCard>
        </div>
    </div>
</template>

<script setup lang="ts">
import type { Entity } from "~/types/entity";
import type { SelectionState, MetadataEditState } from "~/types/api";
import EntityMetadata from "./EntityMetadata.vue";

// Import schema utilities for dynamic entity handling

/**
 * Entity List Component
 * Handles entity display, selection, metadata expansion, and infinite scroll
 */

interface Props {
    entities: Entity[];
    selectionState: SelectionState;
    metadataEditState: Record<number, MetadataEditState>;
    activeFilters?: Record<string, string>;
}

interface Emits {
    (e: "toggleEntitySelection" | "toggleMetadata" | "cancelEdit" | "refreshEntity", entityId: number): void;
    (e: "saveMetadata", entityId: number, editedJson?: string): void;
    (e: "enterEditMode", entityId: number, metadata: Record<string, unknown>): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Composables
const { formatTimestamp, getPrimaryKeyValue } = useUtils();
const { getEntityBadges } = useEntityBadges();

// Helper function to get entity ID
function getEntityId(entity: Entity): number {
    const id = getPrimaryKeyValue(entity);
    if (!id || id <= 0) {
        console.warn("Entity has invalid ID:", { entity, entity_id: entity.entity_id });
        return -1; // Use -1 to indicate invalid ID instead of 0
    }
    return id;
}

// Helper function to check if entity was actually edited
function wasEntityEdited(entity: Entity): boolean {
    if (!entity.last_edited_at || !entity.created_at) return false;

    // Ensure we have valid date strings
    if (typeof entity.last_edited_at !== "string" || typeof entity.created_at !== "string") return false;

    // Parse dates and compare timestamps
    const created = new Date(entity.created_at).getTime();
    const edited = new Date(entity.last_edited_at).getTime();

    // Consider edited if there's more than 1 second difference (to account for minor timing differences)
    return Math.abs(edited - created) > 1000;
}

// Helper function to generate tooltip for edited entities
function getEditedTooltip(entity: Entity): string {
    if (!entity.last_edited_at) return "";

    let tooltip = `Last edited: ${formatTimestamp(entity.last_edited_at)}`;

    if (entity.edited_by_name) {
        tooltip += `\nEdited by: ${entity.edited_by_name}`;
    }

    return tooltip;
}

// Methods
function toggleEntitySelection(entityId: number): void {
    emit("toggleEntitySelection", entityId);
}

function toggleMetadata(entityId: number): void {
    emit("toggleMetadata", entityId);
}

function enterEditMode(entityId: number, metadata: Record<string, unknown>): void {
    emit("enterEditMode", entityId, metadata);
}

function cancelEdit(entityId: number): void {
    emit("cancelEdit", entityId);
}

function saveMetadata(entityId: number, editedJson?: string): void {
    emit("saveMetadata", entityId, editedJson);
}

function refreshEntity(entityId: number): void {
    emit("refreshEntity", entityId);
}

function isEntitySelected(entityId: number): boolean {
    return props.selectionState.selectedEntities.has(entityId);
}

function isMetadataExpanded(entityId: number): boolean {
    return props.selectionState.expandedMetadata.has(entityId);
}

function handleRowClick(event: MouseEvent, entityId: number): void {
    // Don't trigger row click if text is being selected
    const selection = window.getSelection();
    if (selection && selection.toString().length > 0) {
        return;
    }

    // Don't trigger row click for interactive elements
    const target = event.target as HTMLElement;
    if (target.closest("button, a, input")) {
        return;
    }

    toggleMetadata(entityId);
}

function handleEntityKeydown(event: KeyboardEvent, entityId: number): void {
    switch (event.key) {
        case "Enter":
        case " ":
            // Toggle metadata on Enter or Space
            event.preventDefault();
            toggleMetadata(entityId);
            break;
        case "s":
        case "S":
            // Toggle selection on 's' key (like checkbox)
            event.preventDefault();
            toggleEntitySelection(entityId);
            break;
    }
}
</script>
