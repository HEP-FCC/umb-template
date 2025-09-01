<template>
    <UModal
        v-model:open="isOpen"
        title="Admin Tools"
        :transition="true"
        :close="{
            color: 'neutral',
            variant: 'ghost',
            size: 'xs',
            class: 'w-6 h-6 p-1 hover:bg-gray-100 rounded cursor-pointer shrink-0 flex items-center justify-center',
        }"
    >
        <UButton
            class="cursor-pointer"
            icon="i-heroicons-cog-6-tooth"
            color="neutral"
            variant="ghost"
            :label="iconOnly ? undefined : 'Admin'"
            @click="isOpen = true"
        />

        <template #body>
            <div class="space-y-6 overflow-hidden">
                <!-- Admin Override Section -->
                <div class="space-y-3">
                    <h3 class="text-md font-medium text-deep-blue-900 flex items-center gap-2">
                        <UIcon name="i-heroicons-cog-6-tooth" class="text-lg text-secondary-500" />
                        Override entity metadata with data from a JSON file
                        <UTooltip
                            text="Learn more about the override functionality"
                            class="cursor-pointer"
                            :popper="{ placement: 'bottom' }"
                        >
                            <UButton
                                variant="ghost"
                                color="primary"
                                size="xl"
                                class="w-8 h-8 hover:bg-gray-100 rounded-full flex items-center justify-center cursor-pointer"
                                @click="showOverrideHelp = !showOverrideHelp"
                            >
                                <UIcon
                                    name="i-heroicons-information-circle"
                                    style="
                                        width: 24px !important;
                                        height: 24px !important;
                                        min-width: 24px !important;
                                        min-height: 24px !important;
                                    "
                                />
                            </UButton>
                        </UTooltip>
                    </h3>

                    <!-- Expandable Help Section with Transition -->
                    <div
                        class="transition-all duration-300 ease-in-out overflow-hidden"
                        :style="{
                            maxHeight: showOverrideHelp ? '50rem' : '0',
                            opacity: showOverrideHelp ? '1' : '0',
                        }"
                    >
                        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-deep-blue-900 flex items-center gap-2">
                                    <UIcon name="i-heroicons-academic-cap" class="text-deep-blue-600" />
                                    How Override Works
                                </h4>
                                <UButton
                                    icon="i-heroicons-x-mark"
                                    color="neutral"
                                    variant="ghost"
                                    size="xs"
                                    class="w-6 h-6 p-1 hover:bg-gray-100 rounded cursor-pointer flex items-center justify-center shrink-0"
                                    @click="showOverrideHelp = false"
                                />
                            </div>

                            <div class="text-sm text-deep-blue-800 space-y-2">
                                <p>
                                    <strong>⚠️ UUID Required:</strong> Each entity MUST include a valid 'uuid' field.
                                    Entities without UUIDs will be rejected.
                                </p>
                                <p>
                                    <strong>📃 Metadata Only:</strong> Only metadata fields can be updated. Database
                                    fields like foreign keys, names, UUIDs are protected and blocked.
                                </p>
                                <p>
                                    <strong>🔒 Field Locking:</strong> Updated metadata fields are automatically locked
                                    to prevent further changes (unless force override is used).
                                </p>
                                <p>
                                    <strong>🔄 Transaction Safety:</strong> All updates happen in one transaction - if
                                    any entity fails, nothing is changed.
                                </p>
                            </div>

                            <div class="space-y-2">
                                <h5 class="font-medium text-deep-blue-900">Example JSON Format:</h5>
                                <pre
                                    class="bg-gray-100 p-3 rounded text-sm font-mono overflow-x-auto text-deep-blue-800"
                                >
[
  {
    "uuid": "valid-entity-uuid-here",
    "description": "Updated description",
    "process-name": "new-simulation",
    "status": "completed",
  },
  {
    "uuid": "another-valid-entity-uuid-here",
    "comment": "Updated via bulk override",
    "status": "done",
  }
]</pre
                                >
                            </div>

                            <div
                                class="text-sm text-shadow-amber-200 text-amber-700 bg-amber-100 p-2 rounded border border-amber-200"
                            >
                                <strong>⚠️ Important:</strong> Every entity must have a 'uuid' field. Only metadata
                                fields will be processed - all database fields (foregin keys) are.
                            </div>
                        </div>
                    </div>

                    <div class="space-y-2">
                        <!-- File Selection -->
                        <div class="flex items-center gap-2">
                            <UButton
                                icon="i-heroicons-folder-open"
                                color="neutral"
                                variant="outline"
                                size="sm"
                                class="cursor-pointer"
                                @click="triggerFileInput"
                            >
                                Select JSON File
                            </UButton>
                        </div>

                        <!-- Hidden file input -->
                        <input
                            ref="fileInput"
                            type="file"
                            accept=".json"
                            class="hidden"
                            @change="handleFileSelection"
                        />

                        <!-- Force Override Checkbox -->
                        <div class="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                            <UCheckbox id="force-override" v-model="forceOverride" color="warning" />
                            <label for="force-override" class="flex items-center gap-2 text-sm cursor-pointer">
                                <UIcon name="i-heroicons-exclamation-triangle" class="text-lg text-amber-600" />
                                <span class="font-medium text-md text-amber-800">Force Override Locked Fields</span>
                                <span
                                    class="inline-flex items-center cursor-pointer"
                                    title="When enabled, this will override entity values even if the fields are currently locked by other users. Use with caution - this can overwrite changes made by other users and may cause data conflicts."
                                >
                                    <UIcon
                                        name="i-heroicons-information-circle"
                                        class="text-amber-600 hover:text-amber-800 cursor-help"
                                        style="
                                            width: 24px !important;
                                            height: 24px !important;
                                            min-width: 24px !important;
                                            min-height: 24px !important;
                                        "
                                    />
                                </span>
                            </label>
                        </div>

                        <!-- Override Button -->
                        <UButton
                            icon="i-heroicons-arrow-up-tray"
                            color="primary"
                            variant="solid"
                            size="sm"
                            :disabled="!selectedFile || isProcessing"
                            :loading="isProcessing"
                            class="cursor-pointer"
                            @click="confirmOverride"
                        >
                            {{ isProcessing ? "Processing..." : "Override Entities" }}
                        </UButton>

                        <!-- Status Messages -->
                        <div v-if="statusMessage" class="text-xs text-secondary" :class="statusMessageClass">
                            {{ statusMessage }}
                        </div>

                        <!-- Lock Conflicts Details -->
                        <div v-if="lockConflicts && lockConflicts.length > 0" class="mt-4 space-y-3">
                            <div class="flex items-center justify-between">
                                <h4 class="text-sm font-medium text-red-800 flex items-center gap-2">
                                    <UIcon name="i-heroicons-lock-closed" class="text-red-600" />
                                    Lock Conflicts Details:
                                </h4>
                                <UButton
                                    icon="i-heroicons-clipboard-document"
                                    color="neutral"
                                    variant="outline"
                                    size="xs"
                                    class="cursor-pointer"
                                    @click="copyLockConflictsToClipboard"
                                >
                                    Copy JSON
                                </UButton>
                            </div>
                            <div class="max-h-64 overflow-y-auto space-y-3">
                                <div
                                    v-for="(conflict, index) in lockConflicts"
                                    :key="conflict.entity_uuid"
                                    class="border border-red-300 rounded-lg p-4 bg-red-50 shadow-sm"
                                >
                                    <div class="text-sm font-semibold text-red-900 mb-3 pb-2 border-b border-red-200">
                                        <div class="flex items-center gap-2">
                                            <span class="bg-red-100 text-red-800 px-2 py-1 rounded text-xs font-medium">
                                                Entity #{{ index + 1 }}
                                            </span>
                                            <span class="text-red-800">{{
                                                conflict.entity_data?.name || "Unknown"
                                            }}</span>
                                        </div>
                                        <div class="text-xs text-red-600 font-mono mt-1">
                                            UUID: {{ conflict.entity_uuid }}
                                        </div>
                                    </div>
                                    <div class="space-y-3">
                                        <div
                                            v-for="(fieldInfo, fieldName) in conflict.locked_fields"
                                            :key="fieldName"
                                            class="bg-white rounded border border-red-200 p-3"
                                        >
                                            <div class="flex items-center gap-2 mb-2">
                                                <UIcon name="i-heroicons-lock-closed" class="text-energy-500 text-xs" />
                                                <span class="font-bold text-energy-800 text-sm">{{ fieldName }}</span>
                                                <span
                                                    class="text-xs bg-energy-100 text-energy-700 px-2 py-1 rounded font-medium"
                                                    >LOCKED</span
                                                >
                                            </div>
                                            <div class="text-xs space-y-1 ml-5">
                                                <div class="flex items-start gap-2">
                                                    <span class="font-medium text-dark-blue-900 min-w-[80px]"
                                                        >Current:</span
                                                    >
                                                    <span
                                                        class="font-mono bg-gray-100 px-2 py-1 rounded text-dark-blue-900 break-all"
                                                    >
                                                        {{ fieldInfo.current_value ?? "null" }}
                                                    </span>
                                                </div>
                                                <div class="flex items-start gap-2">
                                                    <span class="font-medium text-energy min-w-[80px]">Attempted:</span>
                                                    <span
                                                        class="font-mono bg-energy-50 px-2 py-1 rounded text-energy break-all"
                                                    >
                                                        {{ fieldInfo.attempted_value ?? "null" }}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </UModal>
</template>

<script setup lang="ts">
interface Props {
    iconOnly?: boolean;
}

withDefaults(defineProps<Props>(), {
    iconOnly: false,
});

const isOpen = ref(false);

// API client
const { typedFetch } = useApiClient();

// Override response type
interface OverrideResponse {
    success: boolean;
    message: string;
    updated_count: number;
    lock_conflicts?: Array<{
        entity_id: number;
        entity_uuid: string;
        locked_fields: Record<
            string,
            {
                locked: boolean;
                current_value: unknown;
                attempted_value: unknown;
            }
        >;
        entity_data: Record<string, unknown>;
    }>;
    updated_entities?: Array<Record<string, unknown>>;
    missing_entities?: Array<{
        entity_data: Record<string, unknown>;
        identifier: string;
    }>;
}

// File upload and override functionality
const fileInput = ref<HTMLInputElement>();
const selectedFile = ref<File | null>(null);
const selectedFileName = ref<string>("");
const isProcessing = ref(false);
const statusMessage = ref<string>("");
const statusMessageClass = ref<string>("");
const lockConflicts = ref<OverrideResponse["lock_conflicts"]>([]);
const forceOverride = ref<boolean>(false);
const showOverrideHelp = ref<boolean>(false);

// Trigger file input click
const triggerFileInput = () => {
    fileInput.value?.click();
};

// Handle file selection
const handleFileSelection = (event: Event) => {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];

    if (file) {
        selectedFile.value = file;
        selectedFileName.value = file.name;
        statusMessage.value = "";

        // Validate file type
        if (!file.name.toLowerCase().endsWith(".json")) {
            showStatus("Please select a valid JSON file.", "error");
            return;
        }

        // Validate file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            showStatus("File size must be less than 10MB.", "error");
            return;
        }

        showStatus(`Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`, "success");
    }
};

// Show status message with styling
const showStatus = (message: string, type: "success" | "error" | "info") => {
    statusMessage.value = message;
    statusMessageClass.value =
        type === "success" ? "text-green-600" : type === "error" ? "text-energy-600" : "text-blue-600";
};

// Confirm override operation
const confirmOverride = () => {
    const baseMessage =
        "Are you sure you want to override entity metadata? This operation will:\n\n" +
        "• Require a valid UUID for each entity\n" +
        "• Update ONLY metadata fields (database fields are protected)\n" +
        "• Create field locks to prevent further modifications\n" +
        "• Fail if any entities don't exist or lack UUIDs\n" +
        "• Cannot be easily undone\n";

    const forceMessage = forceOverride.value
        ? "\n⚠️  FORCE OVERRIDE ENABLED: This will ignore existing field locks and may overwrite changes made by other users!\n"
        : "";

    const confirmed = confirm(baseMessage + forceMessage + "\nPlease confirm to proceed.");

    if (confirmed) {
        performOverride();
    }
};

// Perform the override operation
const performOverride = async () => {
    if (!selectedFile.value) {
        showStatus("No file selected.", "error");
        return;
    }

    isProcessing.value = true;
    showStatus("Reading and validating file...", "info");

    try {
        // Read file as text
        const fileText = await selectedFile.value.text();

        // Parse JSON
        let entities;
        try {
            entities = JSON.parse(fileText);
        } catch {
            throw new Error("Invalid JSON format in selected file.");
        }

        // Validate that it's an array
        if (!Array.isArray(entities)) {
            throw new Error("JSON file must contain an array of entities.");
        }

        if (entities.length === 0) {
            throw new Error("JSON file contains no entities.");
        }

        showStatus(`Processing ${entities.length} entities...`, "info");

        // Send to backend with force_override query parameter
        const response = await typedFetch<OverrideResponse>("/override", {
            method: "POST",
            body: entities,
            query: { force_override: forceOverride.value },
        });

        if (response.success) {
            const successMsg = forceOverride.value
                ? `Successfully updated ${response.updated_count} entities (forced override enabled).`
                : `Successfully updated ${response.updated_count} entities.`;

            showStatus(successMsg, "success");
            lockConflicts.value = []; // Clear any previous conflicts

            // Clear the file selection after successful operation
            setTimeout(() => {
                selectedFile.value = null;
                selectedFileName.value = "";
                forceOverride.value = false; // Reset force override
                if (fileInput.value) {
                    fileInput.value.value = "";
                }
            }, 3000);
        } else {
            if (response.missing_entities && response.missing_entities.length > 0) {
                // Handle missing entities/UUIDs error
                const missingCount = response.missing_entities.length;
                const missingList = response.missing_entities
                    .slice(0, 3)
                    .map((missing) => missing.identifier)
                    .join(", ");
                const moreText = missingCount > 3 ? ` and ${missingCount - 3} more` : "";

                showStatus(
                    `Operation failed: ${missingCount} entities have issues (${missingList}${moreText}). Each entity must have a valid UUID.`,
                    "error",
                );
                lockConflicts.value = [];
            } else if (response.lock_conflicts && response.lock_conflicts.length > 0) {
                lockConflicts.value = response.lock_conflicts;

                // Count total locked fields across all entities
                const totalLockedFields = response.lock_conflicts.reduce(
                    (sum, conflict) => sum + Object.keys(conflict.locked_fields).length,
                    0,
                );

                showStatus(
                    `Operation failed: ${response.lock_conflicts.length} entities have ${totalLockedFields} locked fields. See details below.`,
                    "error",
                );

                // Log detailed conflict information for debugging
                console.warn("Lock conflicts detected:", response.lock_conflicts);
            } else {
                lockConflicts.value = [];
                showStatus(response.message || "Override operation failed.", "error");
            }
        }
    } catch (error: unknown) {
        console.error("Override operation failed:", error);
        const errorMessage =
            (error as { data?: { detail?: string }; message?: string })?.data?.detail ||
            (error as { message?: string })?.message ||
            "Failed to process override operation.";
        showStatus(errorMessage, "error");
    } finally {
        isProcessing.value = false;
    }
};

// Copy lock conflicts to clipboard as formatted JSON
const copyLockConflictsToClipboard = async () => {
    if (!lockConflicts.value || lockConflicts.value.length === 0) {
        showStatus("No lock conflicts to copy.", "error");
        return;
    }

    try {
        // Create a structured JSON object with detailed conflict information
        const conflictData = {
            summary: {
                total_conflicts: lockConflicts.value.length,
                total_locked_fields: lockConflicts.value.reduce(
                    (sum, conflict) => sum + Object.keys(conflict.locked_fields).length,
                    0,
                ),
                timestamp: new Date().toISOString(),
            },
            conflicts: lockConflicts.value.map((conflict, index) => ({
                entity_number: index + 1,
                entity_id: conflict.entity_id,
                entity_uuid: conflict.entity_uuid,
                entity_name: conflict.entity_data?.name || "Unknown",
                locked_fields: Object.entries(conflict.locked_fields).map(([fieldName, fieldInfo]) => ({
                    field_name: fieldName,
                    is_locked: fieldInfo.locked,
                    current_value: fieldInfo.current_value,
                    attempted_value: fieldInfo.attempted_value,
                    value_type_current: typeof fieldInfo.current_value,
                    value_type_attempted: typeof fieldInfo.attempted_value,
                })),
                entity_metadata: conflict.entity_data,
            })),
        };

        // Format as pretty JSON
        const jsonString = JSON.stringify(conflictData, null, 2);

        // Copy to clipboard
        await navigator.clipboard.writeText(jsonString);

        showStatus(`Copied ${lockConflicts.value.length} lock conflicts to clipboard as JSON.`, "success");
    } catch (error) {
        console.error("Failed to copy to clipboard:", error);
        showStatus("Failed to copy to clipboard. Check console for details.", "error");
    }
};
</script>
