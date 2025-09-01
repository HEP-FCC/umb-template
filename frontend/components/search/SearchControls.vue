<template>
    <div class="space-y-2">
        <label class="block text-sm font-medium">
            Search Query
            <span v-if="showFilterNote" class="text-xs ml-1">
                (Additional filters from navigation applied automatically)
            </span>
        </label>
        <div class="flex gap-2 items-center">
            <!-- Help Icons Container - moved to the left -->
            <div class="relative">
                <!-- Query Language Help Icon -->
                <UPopover
                    v-model:open="showHelpTooltip"
                    :content="{ side: 'bottom', sideOffset: 20 }"
                    mode="click"
                    :dismissible="true"
                >
                    <template #content>
                        <div
                            class="w-80 sm:max-w-md p-3 sm:p-4 bg-white rounded-lg shadow-lg max-h-[80vh] overflow-y-auto"
                        >
                            <div class="flex items-center justify-between mb-3">
                                <div class="font-semibold text-sm">Query Language Help</div>
                                <UButton
                                    icon="i-heroicons-x-mark"
                                    color="neutral"
                                    variant="ghost"
                                    size="xs"
                                    class="w-6 h-6 p-1 hover:bg-gray-100 rounded cursor-pointer flex items-center justify-center shrink-0"
                                    @click="closeModal"
                                />
                            </div>
                            <div class="text-xs space-y-3">
                                <div>
                                    <div class="font-medium mb-2">Global Search:</div>
                                    <div class="space-y-1.5">
                                        <div>
                                            <code :class="codeClass">H to cu</code>
                                            - Substring match across all fields (case-insensitive)
                                        </div>
                                        <div>
                                            <code :class="codeClass">"H to cu [0-9]+"</code>
                                            - Regex pattern match across all fields (case-insensitive)
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <div class="font-medium mb-2">Field-specific queries:</div>
                                    <div class="space-y-1.5">
                                        <div>
                                            <code :class="codeClass">description:"ee -> Z(nu nu)"</code>
                                            - Metadata text field
                                        </div>
                                        <div>
                                            <code :class="codeClass">sum-of-weights>100000</code>
                                            - Metadata number filter
                                        </div>
                                        <div>
                                            <code :class="codeClass">name#"H to cu"</code>
                                            - Fuzzy text match (0.7 similarity)
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <div class="font-medium mb-2">Boolean Operators:</div>
                                    <div class="flex flex-wrap gap-1">
                                        <code :class="codeClass">AND</code>
                                        <code :class="codeClass">OR</code>
                                        <code :class="codeClass">NOT</code>
                                    </div>
                                </div>
                                <div>
                                    <div class="font-medium mb-2">Comparison Operators:</div>
                                    <div class="flex flex-wrap gap-1">
                                        <code :class="codeClass">=</code>
                                        <code :class="codeClass">!=</code>
                                        <code :class="codeClass">&gt;</code>
                                        <code :class="codeClass">&lt;</code>
                                        <code :class="codeClass">&gt;=</code>
                                        <code :class="codeClass">&lt;=</code>
                                    </div>
                                    <div class="text-xs mt-2">
                                        <div>
                                            <code :class="codeClass">:</code>
                                            substring,
                                            <code :class="codeClass">!:</code>
                                            not substring,
                                            <code :class="codeClass">=~</code>
                                            regex match,
                                            <code :class="codeClass">!~</code>
                                            regex not match,
                                            <code :class="codeClass">#</code>
                                            fuzzy match (0.7),
                                            <code :class="codeClass">:*</code>
                                            field exists,
                                            <code :class="codeClass">!:*</code>
                                            field not exists
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <div class="font-medium mb-2">Autocomplete:</div>
                                    <div class="text-xs">
                                        <div>• Shows automatically while typing or when field is empty</div>
                                        <div>
                                            • Press <code :class="codeClass">Ctrl+Space</code> for enhanced suggestions
                                        </div>
                                        <div>• Pasting text won't trigger suggestions</div>
                                    </div>
                                </div>
                                <div class="pt-2 border-t border-gray-200 text-center">
                                    <a
                                        href="https://cloud.google.com/logging/docs/view/logging-query-language"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="hover:text-secondary-700 cursor-pointer hover:underline text-xs font-medium transition-colors inline-flex items-center gap-1"
                                    >
                                        View Full Documentation
                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path
                                                stroke-linecap="round"
                                                stroke-linejoin="round"
                                                stroke-width="2"
                                                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                                            />
                                        </svg>
                                    </a>
                                </div>
                            </div>
                        </div>
                    </template>
                    <UTooltip text="Learn more about the query language">
                        <UButton
                            color="primary"
                            variant="ghost"
                            size="xl"
                            class="w-8 h-8 hover:bg-gray-100 rounded-full flex items-center justify-center cursor-pointer"
                        >
                            <UIcon
                                name="i-heroicons-information-circle"
                                style="
                                    width: 28px !important;
                                    height: 28px !important;
                                    min-width: 28px !important;
                                    min-height: 28px !important;
                                "
                            />
                        </UButton>
                    </UTooltip>
                </UPopover>
            </div>

            <div class="flex-grow relative">
                <SearchInputWithAutocomplete
                    v-model="searchQuery"
                    :placeholder="searchPlaceholderText"
                    input-class="w-full"
                    @enter="$emit('search')"
                />
            </div>
            <UButton color="primary" variant="solid" size="lg" class="cursor-pointer" @click="$emit('search')">
                Search
            </UButton>
            <div class="relative">
                <UTooltip text="Copy link" placement="top" class="cursor-pointer">
                    <UButton
                        color="neutral"
                        variant="outline"
                        size="lg"
                        :loading="isPermalinkCopyInProgress"
                        :disabled="!canCopyLink"
                        @click="handleCopyPermalink"
                    >
                        Copy
                    </UButton>
                </UTooltip>
                <div
                    v-if="showLinkCopiedFeedback"
                    class="absolute -top-8 left-1/2 transform -translate-x-1/2 bg-primary text-white text-xs px-2 py-1 rounded shadow-lg whitespace-nowrap z-10"
                >
                    Link copied!
                </div>
            </div>
        </div>

        <UAlert
            v-if="searchError"
            color="error"
            variant="soft"
            icon="i-heroicons-exclamation-triangle"
            :title="getErrorTitle(searchError)"
            :description="getErrorDescription(searchError)"
            closable
            @close="$emit('clearError')"
        />

        <UAlert
            v-if="!apiAvailable"
            color="warning"
            variant="soft"
            icon="i-heroicons-exclamation-triangle"
            title="API Server Unavailable"
            description="Unable to connect to the backend server. Please check if the server is running."
        />
    </div>
</template>

<script setup lang="ts">
import SearchInputWithAutocomplete from "./SearchInputWithAutocomplete.vue";

interface Props {
    searchQuery: string;
    searchPlaceholderText: string;
    showFilterNote: boolean;
    canCopyLink: boolean;
    searchError: string | null;
    apiAvailable: boolean;
}

interface Emits {
    (e: "update:searchQuery", value: string): void;
    (e: "search" | "clearError"): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Search query model with emit on update
const searchQuery = computed({
    get: () => props.searchQuery,
    set: (value: string) => emit("update:searchQuery", value),
});

// UI state for permalink functionality
const isPermalinkCopyInProgress = ref(false);
const showLinkCopiedFeedback = ref(false);
const showHelpTooltip = ref(false);
const codeClass = "bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono";

// Utility functions
const { copyToClipboard } = useUtils();

/**
 * Show success notification for link copied
 */
function showSuccessNotification(): void {
    showLinkCopiedFeedback.value = true;
    setTimeout(() => {
        showLinkCopiedFeedback.value = false;
    }, 2000);
}

/**
 * Close the help modal
 */
function closeModal(): void {
    showHelpTooltip.value = false;
}

/**
 * Generate shareable permalink URL with current search state
 */
const generatePermalinkUrl = (): string => {
    const currentUrl = new URL(window.location.href);
    const params = new URLSearchParams();

    if (props.searchQuery.trim()) params.set("q", props.searchQuery.trim());

    const baseUrl = `${currentUrl.origin}${currentUrl.pathname}`;
    const queryString = params.toString();
    return queryString ? `${baseUrl}?${queryString}` : baseUrl;
};

/**
 * Handle permalink copy action with loading states
 */
async function handleCopyPermalink(): Promise<void> {
    if (isPermalinkCopyInProgress.value) return;

    try {
        isPermalinkCopyInProgress.value = true;
        const permalinkUrl = generatePermalinkUrl();
        await copyToClipboard(permalinkUrl);
        showSuccessNotification();
    } catch (error) {
        console.error("Failed to copy permalink:", error);
    } finally {
        isPermalinkCopyInProgress.value = false;
    }
}

/**
 * Get appropriate error title based on error message
 */
function getErrorTitle(errorMessage: string): string {
    // Check for specific error patterns to provide better titles
    if (errorMessage.toLowerCase().includes("field") && errorMessage.toLowerCase().includes("not available")) {
        return "Invalid Field";
    }
    if (errorMessage.toLowerCase().includes("operation") && errorMessage.toLowerCase().includes("cannot be used")) {
        return "Invalid Operation";
    }
    if (errorMessage.toLowerCase().includes("syntax")) {
        return "Syntax Error";
    }
    if (errorMessage.toLowerCase().includes("query")) {
        return "Search Error";
    }
    return "Search Error";
}

/**
 * Get appropriate error description with helpful context
 */
function getErrorDescription(errorMessage: string): string {
    // If the error message is already user-friendly, use it as is
    if (errorMessage.includes("field") && errorMessage.includes("not available")) {
        return `${errorMessage} You can check the available fields using the help tooltip above.`;
    }
    if (errorMessage.includes("operation") && errorMessage.includes("cannot be used")) {
        return `${errorMessage} Try using '=' for exact match, ':' for contains, or '=~' for regex patterns.`;
    }
    if (errorMessage.includes("syntax")) {
        return `${errorMessage} Check the search syntax guide in the help tooltip above.`;
    }

    // For generic errors, provide helpful context
    return `${errorMessage} Please check your search syntax and try again. You can use the help tooltip above for syntax examples.`;
}
</script>
