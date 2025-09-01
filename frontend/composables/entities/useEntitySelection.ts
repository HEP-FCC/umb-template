// Auto-imported: ref, reactive, shallowReactive, computed
import type { Entity, SelectionState, MetadataEditState } from "~/types/api";
import type { SearchOptions } from "~/types/composables";
// Auto-imported: getPrimaryKeyValue, extractEntityIds

/**
 * Generic entity selection and metadata management composable
 * Handles entity selection, metadata expansion, and download functionality
 * Works with any entity type (books, products, etc.)
 */
export function useEntitySelection() {
    const { downloadEntitiesByIds, downloadFilteredEntities } = useApiClient();

    // Check API availability
    const apiAvailable = computed(() => {
        const config = useRuntimeConfig();
        return !!(config.public.apiBaseUrl || "http://localhost:8000");
    });

    const { createEntityDownloadFilename, downloadAsJsonFile } = useUtils();

    // Entity selection and UI expansion state
    const selectionState = reactive<SelectionState>({
        selectedIds: new Set<number>(),
        selectedEntities: new Set<number>(),
        expandedMetadata: new Set<number>(),
        selectAll: false,
        isIndeterminate: false,
        isDownloading: false,
    });

    // Additional state for filtered download
    const isDownloadingFiltered = ref(false);

    // Force reactivity triggers for Set changes
    const selectedEntitiesVersion = ref(0);
    const expandedMetadataVersion = ref(0);

    // Metadata editing state - per-entity editing context
    const metadataEditState = reactive<Record<number, MetadataEditState>>({});

    // Computed properties for better reactivity
    const selectedCount = computed(() => {
        void selectedEntitiesVersion.value; // Force reactivity
        return selectionState.selectedEntities.size;
    });

    const expandedMetadataList = computed(() => {
        void expandedMetadataVersion.value; // Force reactivity
        return Array.from(selectionState.expandedMetadata);
    });

    const selectedEntityList = computed(() => {
        void selectedEntitiesVersion.value; // Force reactivity
        return Array.from(selectionState.selectedEntities);
    });

    function getAllEntitiesSelected(entities: Entity[]) {
        if (entities.length === 0) return false;

        const currentEntityIds = extractEntityIds(entities);
        return (
            currentEntityIds.length > 0 &&
            currentEntityIds.every((id: number) => selectionState.selectedEntities.has(id))
        );
    }
    function getAllMetadataExpanded(entities: Entity[]) {
        // Access the reactive version to trigger re-computation
        void expandedMetadataVersion.value;
        const currentEntityIds = extractEntityIds(entities);
        return (
            currentEntityIds.length > 0 &&
            currentEntityIds.every((id: number) => selectionState.expandedMetadata.has(id))
        );
    }

    /**
     * Toggle individual entity selection
     */
    function toggleEntitySelection(entityIdOrData: number | Entity): void {
        const entityId = typeof entityIdOrData === "number" ? entityIdOrData : getPrimaryKeyValue(entityIdOrData);

        if (entityId === null) return;

        if (selectionState.selectedEntities.has(entityId)) {
            selectionState.selectedEntities.delete(entityId);
        } else {
            selectionState.selectedEntities.add(entityId);
        }
        selectedEntitiesVersion.value++;
    }

    /**
     * Toggle select all entities on current page
     */
    function toggleSelectAll(entities: Entity[]): void {
        const currentEntityIds = extractEntityIds(entities);
        const allSelected = currentEntityIds.every((id: number) => selectionState.selectedEntities.has(id));

        if (allSelected) {
            currentEntityIds.forEach((id: number) => selectionState.selectedEntities.delete(id));
        } else {
            currentEntityIds.forEach((id: number) => selectionState.selectedEntities.add(id));
        }
        selectedEntitiesVersion.value++;
    }

    /**
     * Toggle metadata expansion for a specific entity
     */
    function toggleMetadata(entityIdOrData: number | Entity): void {
        const entityId = typeof entityIdOrData === "number" ? entityIdOrData : getPrimaryKeyValue(entityIdOrData);

        if (entityId === null) return;

        if (selectionState.expandedMetadata.has(entityId)) {
            selectionState.expandedMetadata.delete(entityId);
        } else {
            selectionState.expandedMetadata.add(entityId);
        }
        expandedMetadataVersion.value++;
    }

    /**
     * Toggle all metadata expansions - optimized for large entity lists
     */
    function toggleAllMetadata(entities: Entity[]): void {
        const currentEntityIds = extractEntityIds(entities);
        const allExpanded =
            currentEntityIds.length > 0 &&
            currentEntityIds.every((id: number) => selectionState.expandedMetadata.has(id));

        if (allExpanded) {
            // Batch removal for better performance
            currentEntityIds.forEach((id: number) => selectionState.expandedMetadata.delete(id));
        } else {
            // Batch addition - use Set operations for efficiency
            const newExpandedSet = new Set(selectionState.expandedMetadata);
            currentEntityIds.forEach((id: number) => newExpandedSet.add(id));
            selectionState.expandedMetadata = newExpandedSet;
        }
        expandedMetadataVersion.value++;
    }

    /**
     * Clear all metadata expansions
     */
    function clearMetadataExpansions(): void {
        selectionState.expandedMetadata.clear();
        expandedMetadataVersion.value++;
    }

    /**
     * Check if entity is selected
     */
    function isEntitySelected(entityId: number): boolean {
        // Access the reactive version to trigger re-computation
        void selectedEntitiesVersion.value;
        return selectionState.selectedEntities.has(entityId);
    }

    /**
     * Check if metadata is expanded for entity
     */
    function isMetadataExpanded(entityId: number): boolean {
        // Force reactivity check
        void selectedEntitiesVersion.value;
        return selectionState.expandedMetadata.has(entityId);
    }
    /**
     * Download selected entities as JSON file
     */
    async function downloadSelectedEntities(): Promise<void> {
        const selectedEntityIds = Array.from(selectionState.selectedEntities);
        if (selectedEntityIds.length === 0) {
            return;
        }

        selectionState.isDownloading = true;
        try {
            const entitiesToDownload = await downloadEntitiesByIds(selectedEntityIds);

            if (entitiesToDownload.length > 0) {
                const filename = createEntityDownloadFilename(entitiesToDownload.length);
                downloadAsJsonFile(entitiesToDownload, filename);
            }
        } catch (error) {
            console.error("Failed to download entities:", error);
            // Error interceptor will handle user notification
            throw error;
        } finally {
            selectionState.isDownloading = false;
        }
    }

    /**
     * Download all filtered entities as JSON file
     */
    async function downloadAllFilteredEntities(searchOptions: SearchOptions): Promise<void> {
        isDownloadingFiltered.value = true;
        try {
            const entitiesToDownload = await downloadFilteredEntities(searchOptions);

            if (entitiesToDownload.length > 0) {
                const filename = createEntityDownloadFilename(entitiesToDownload.length);
                downloadAsJsonFile(entitiesToDownload, filename);
            }
        } catch (error) {
            console.error("Failed to download filtered entities:", error);
            // Error interceptor will handle user notification
            throw error;
        } finally {
            isDownloadingFiltered.value = false;
        }
    }

    /**
     * Delete all filtered entities with confirmation
     */
    async function deleteAllFilteredEntities(searchOptions: SearchOptions): Promise<void> {
        const { deleteEntities } = useApiClient();
        const { isAuthenticated, login } = useAuth();
        const toast = useToast();

        // Check if user is authenticated
        if (!isAuthenticated.value) {
            toast.add({
                title: "Authentication Required",
                description: "Please login to delete entities.",
                color: "warning",
            });
            login();
            return;
        }

        try {
            isDownloadingFiltered.value = true; // Reuse this for loading state

            // First, get all filtered entities to find their IDs
            const filteredEntities = await downloadFilteredEntities(searchOptions);

            if (filteredEntities.length === 0) {
                toast.add({
                    title: "No Entities to Delete",
                    description: "No entities match the current filters.",
                    color: "info",
                });
                return;
            }

            // Extract entity IDs
            const entityIds = extractEntityIds(filteredEntities);

            if (entityIds.length === 0) {
                toast.add({
                    title: "Error",
                    description: "Could not extract entity IDs for deletion.",
                    color: "error",
                });
                return;
            }

            const result = await deleteEntities(entityIds);

            if (result.success) {
                toast.add({
                    title: "Deletion Successful",
                    description: `Successfully deleted ${result.deleted_count} entities.${
                        result.not_found_count > 0 ? ` ${result.not_found_count} entities were not found.` : ""
                    }`,
                    color: "success",
                });

                // Clear selection for deleted entities
                if (result.deleted_ids) {
                    result.deleted_ids.forEach((id) => {
                        selectionState.selectedEntities.delete(id);
                        selectionState.expandedMetadata.delete(id);
                    });
                    selectedEntitiesVersion.value++;
                    expandedMetadataVersion.value++;
                }

                // Trigger a page refresh or emit an event to refresh the entity list
                // This will be handled by the parent component
                return;
            } else {
                throw new Error(result.message || "Deletion failed");
            }
        } catch (error: unknown) {
            console.error("Failed to delete filtered entities:", error);
            // Error interceptor will handle user notification
        } finally {
            isDownloadingFiltered.value = false;
        }
    }

    /**
     * Handle row click for metadata toggle
     */
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

    /**
     * Enter edit mode for entity metadata
     */
    function enterEditMode(entityId: number, metadata: Record<string, unknown>): void {
        // Validate entity ID
        if (!entityId || entityId <= 0) {
            console.warn("Cannot enter edit mode for entity with invalid ID:", entityId);
            return;
        }

        metadataEditState[entityId] = {
            isEditing: true,
            editingEntityId: entityId,
            editingData: {},
            hasChanges: false,
            json: JSON.stringify(metadata, null, 2),
            editedJson: JSON.stringify(metadata, null, 2),
            originalMetadata: metadata,
            isSaving: false,
        };
    }

    /**
     * Cancel metadata editing
     */
    function cancelEdit(entityId: number): void {
        if (Object.prototype.hasOwnProperty.call(metadataEditState, entityId)) {
            metadataEditState[entityId].isEditing = false;
            // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
            delete metadataEditState[entityId];
        }
    }

    /**
     * Save metadata changes
     */
    async function saveMetadataChanges(
        entityId: number,
        entities: Entity[],
        updateEntityInArray: (index: number, entity: Entity) => void,
        editedJson?: string,
    ): Promise<void> {
        const editState = metadataEditState[entityId];
        if (!editState) return;

        // Validate entity ID
        if (!entityId || entityId <= 0) {
            const toast = useToast();
            toast.add({
                title: "Invalid Entity",
                description: "Cannot save metadata for entity with invalid ID.",
                color: "error",
            });
            console.error("Attempted to save metadata for invalid entity ID:", entityId);
            return;
        }

        const toast = useToast();
        const { isAuthenticated, login } = useAuth();

        // Check if user is authenticated
        if (!isAuthenticated.value) {
            toast.add({
                title: "Authentication Required",
                description: "Please login to save entity metadata.",
                color: "warning",
            });

            // Trigger login
            login();
            return;
        }

        try {
            // Set saving state
            editState.isSaving = true;

            // Use the edited JSON if provided, otherwise fall back to the edit state JSON
            const jsonToSave = editedJson || editState.editedJson;
            const parsedMetadata = JSON.parse(jsonToSave);

            // Call the backend API to save metadata with cookie-based authentication
            const { updateEntity } = useApiClient();
            await updateEntity(entityId, parsedMetadata);

            toast.add({
                title: "Success",
                description: "Entity metadata updated successfully.",
                color: "success",
            });

            // Update the entity in the local state
            const entityIndex = entities.findIndex((entity: Entity) => getPrimaryKeyValue(entity) === entityId);
            if (entityIndex !== -1) {
                updateEntityInArray(entityIndex, {
                    ...entities[entityIndex],
                    entity_id: entityId,
                    metadata: parsedMetadata,
                });
            }

            // Exit edit mode
            if (Object.prototype.hasOwnProperty.call(metadataEditState, entityId)) {
                // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
                delete metadataEditState[entityId];
            }
        } catch (error: unknown) {
            if (apiAvailable.value) {
                console.error("Failed to save metadata:", error);

                // Rethrow the error so error interceptor can handle it
                throw error;
            } else {
                // API not available - show specific error
                toast.add({
                    title: "API Unavailable",
                    description: "Cannot save metadata - API server is not responding.",
                    color: "error",
                });
            }
        } finally {
            // Clear saving state
            if (editState) {
                editState.isSaving = false;
            }
        }
    }

    /**
     * Calculate textarea rows for metadata editing
     */
    function getTextareaRows(entityId: number): number {
        const editState = metadataEditState[entityId];
        if (!editState) return 10;
        const lineCount = editState.editedJson.split("\n").length;
        return Math.max(10, Math.min(lineCount + 1, 25));
    }

    /**
     * Get selected entities as Entity objects
     * Helper for bulk operations
     */
    function getSelectedEntitiesAsObjects(allEntities: Entity[]): Entity[] {
        return allEntities.filter((entity) => {
            const id = getPrimaryKeyValue(entity);
            return id && selectionState.selectedEntities.has(id);
        });
    }

    /**
     * Clear all selections
     */
    function clearAllSelections(): void {
        selectionState.selectedEntities.clear();
        selectionState.expandedMetadata.clear();
        selectedEntitiesVersion.value++;
        expandedMetadataVersion.value++;
    }

    /**
     * Select entities by IDs
     */
    function selectEntitiesByIds(entityIds: number[]): void {
        entityIds.forEach((id) => selectionState.selectedEntities.add(id));
        selectedEntitiesVersion.value++;
    }

    /**
     * Delete selected entities with confirmation
     */
    async function deleteSelectedEntities(): Promise<void> {
        const selectedEntityIds = Array.from(selectionState.selectedEntities);
        if (selectedEntityIds.length === 0) {
            return;
        }

        const { deleteEntities } = useApiClient();
        const { isAuthenticated, login } = useAuth();
        const toast = useToast();

        // Check if user is authenticated
        if (!isAuthenticated.value) {
            toast.add({
                title: "Authentication Required",
                description: "Please login to delete entities.",
                color: "warning",
            });
            login();
            return;
        }

        // Confirmation is already handled by the calling component
        // No need for additional confirmation dialog here

        try {
            selectionState.isDownloading = true; // Reuse this for delete loading state

            const result = await deleteEntities(selectedEntityIds);

            if (result.success) {
                toast.add({
                    title: "Deletion Successful",
                    description: `Successfully deleted ${result.deleted_count} entities.${
                        result.not_found_count > 0 ? ` ${result.not_found_count} entities were not found.` : ""
                    }`,
                    color: "success",
                });

                // Clear selection for deleted entities
                if (result.deleted_ids) {
                    result.deleted_ids.forEach((id) => {
                        selectionState.selectedEntities.delete(id);
                        selectionState.expandedMetadata.delete(id);
                    });
                    selectedEntitiesVersion.value++;
                    expandedMetadataVersion.value++;
                }

                // Trigger a page refresh or emit an event to refresh the entity list
                // This will be handled by the parent component
                return;
            } else {
                throw new Error(result.message || "Deletion failed");
            }
        } catch (error: unknown) {
            console.error("Failed to delete entities:", error);
            // Error interceptor will handle user notification
        } finally {
            selectionState.isDownloading = false;
        }
    }

    /**
     * Check if metadata is currently being saved for an entity
     */
    function isMetadataSaving(entityId: number): boolean {
        const editState = metadataEditState[entityId];
        return editState?.isSaving ?? false;
    }

    return {
        // State
        selectionState,
        metadataEditState,
        isDownloadingFiltered,

        // Computed
        selectedCount,
        expandedMetadataList,
        selectedEntityList,
        getAllEntitiesSelected,
        getAllMetadataExpanded,

        // Methods
        toggleEntitySelection,
        toggleSelectAll,
        toggleMetadata,
        toggleAllMetadata,
        clearMetadataExpansions,
        isEntitySelected,
        isMetadataExpanded,
        isMetadataSaving,
        downloadSelectedEntities,
        downloadAllFilteredEntities,
        handleRowClick,
        enterEditMode,
        cancelEdit,
        saveMetadataChanges,
        getTextareaRows,

        // New helper methods
        getSelectedEntitiesAsObjects,
        clearAllSelections,
        selectEntitiesByIds,
        deleteSelectedEntities,
        deleteAllFilteredEntities,
    };
}
