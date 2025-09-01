<template>
    <div class="relative">
        <UInput
            ref="inputRef"
            v-model="inputValue"
            :placeholder="placeholder"
            size="lg"
            icon="i-heroicons-magnifying-glass"
            :class="inputClass"
            :ui="{ trailing: 'pe-1' }"
            @keydown="handleKeyDown"
            @input="handleInput"
            @paste="handlePaste"
            @focus="handleFocus"
            @blur="handleBlur"
            @click="handleClick"
        >
            <template v-if="inputValue?.length" #trailing>
                <UButton
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    icon="i-heroicons-x-mark"
                    aria-label="Clear search"
                    class="w-6 h-6 p-1 hover:bg-gray-100 rounded cursor-pointer flex items-center justify-center shrink-0"
                    @click="handleClear"
                />
            </template>
        </UInput>

        <AutocompleteDropdown
            :suggestions="autocomplete.state.suggestions"
            :is-visible="autocomplete.state.isVisible"
            :selected-index="autocomplete.state.selectedIndex"
            :input-element="inputElement"
            @select="handleSuggestionSelect"
            @highlight="handleSuggestionHighlight"
        />
    </div>
</template>

<script setup lang="ts">
// Imports
import AutocompleteDropdown from "./AutocompleteDropdown.vue";

// Types
interface SuggestionItem {
    value: string;
    type: "field" | "operator" | "value";
    description?: string;
}

interface Props {
    modelValue: string;
    placeholder?: string;
    inputClass?: string;
}

interface Emits {
    (e: "update:modelValue", value: string): void;
    (e: "enter" | "focus" | "blur"): void;
}

const props = withDefaults(defineProps<Props>(), {
    placeholder: "Type to search...",
    inputClass: "pr-16 w-full",
});

const emit = defineEmits<Emits>();

// Composables
const autocomplete = useSearchAutocomplete();

// Refs
const inputRef = ref<HTMLInputElement | null>(null);
const cursorPosition = ref(0);
const showAutocompleteOnFocus = ref(false);
const isAutocompleteIntentional = ref(false);
const isContinuousSuggestionMode = ref(false); // Track continuous suggestion mode
const isRecentlyPasted = ref(false); // Track if user just pasted to prevent suggestions

// Computed
const inputValue = computed({
    get: () => props.modelValue,
    set: (value: string) => {
        emit("update:modelValue", value);
        updateCursorPosition();
    },
});

const inputElement = computed(() => {
    const element = inputRef.value;
    if (!element) return null;

    // For UInput component, we need to find the actual input element
    if ("$el" in element) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const uInputEl = (element as any).$el;
        return uInputEl?.querySelector("input") || uInputEl || null;
    }

    // For regular input element
    return element as HTMLInputElement;
});

// Methods
const updateCursorPosition = () => {
    nextTick(() => {
        const input = inputElement.value;
        if (input) {
            cursorPosition.value = input.selectionStart || 0;
        }
    });
};

const handleInput = (event: Event) => {
    const target = event.target as HTMLInputElement;
    cursorPosition.value = target.selectionStart || 0;

    // Use the actual input value from the event target, not the computed prop
    const currentInputValue = target.value;

    // If user recently pasted, always hide suggestions and clear selection
    if (isRecentlyPasted.value) {
        resetAutocompleteState();
        return;
    }

    // Show suggestions in two cases:
    // 1. If we're in continuous suggestion mode (triggered by Ctrl+Space)
    // 2. For normal typing (automatic suggestions)
    if (isContinuousSuggestionMode.value && isAutocompleteIntentional.value) {
        // Continuous mode - keep showing suggestions
        autocomplete.showSuggestions(currentInputValue, cursorPosition.value);
    } else {
        // Normal typing - show automatic suggestions
        isAutocompleteIntentional.value = false; // Mark as automatic suggestion
        autocomplete.showSuggestions(currentInputValue, cursorPosition.value);
    }
};

const handleKeyDown = (event: KeyboardEvent) => {
    // Handle Ctrl+Space to trigger autocomplete
    if (event.ctrlKey && event.key === " ") {
        event.preventDefault();
        triggerAutocomplete();
        return;
    }

    // Handle space key - end continuous suggestion mode
    if (event.key === " " && isContinuousSuggestionMode.value) {
        isContinuousSuggestionMode.value = false;
        isAutocompleteIntentional.value = false;
        autocomplete.hideSuggestions();
        return; // Allow space to be typed normally
    }

    // Handle autocomplete navigation
    if (autocomplete.state.isVisible) {
        switch (event.key) {
            case "ArrowDown":
                event.preventDefault();
                autocomplete.navigateSuggestions("down");
                break;
            case "ArrowUp":
                event.preventDefault();
                autocomplete.navigateSuggestions("up");
                break;
            case "Enter":
                event.preventDefault();
                // End continuous mode first
                isContinuousSuggestionMode.value = false;

                // Apply suggestion if:
                // 1. Suggestions are visible
                // 2. A suggestion is selected
                // 3. Either in continuous mode OR user hasn't recently pasted complex content
                if (autocomplete.state.isVisible && autocomplete.state.selectedIndex >= 0) {
                    const selected = autocomplete.getSelectedSuggestion();
                    if (selected) {
                        // If recently pasted, check if the current input could benefit from suggestions
                        if (isRecentlyPasted.value) {
                            const shouldApply = shouldShowSuggestionsForPastedContent(
                                inputValue.value,
                                inputValue.value,
                            );
                            if (shouldApply) {
                                applySuggestion(selected);
                                return;
                            }
                        } else {
                            // Not recently pasted, normal suggestion application
                            applySuggestion(selected);
                            return;
                        }
                    }
                }

                // In all other cases, perform search
                resetAutocompleteState();
                emit("enter");
                break;
            case "Escape":
                event.preventDefault();
                // End continuous mode and hide suggestions
                isContinuousSuggestionMode.value = false;
                isAutocompleteIntentional.value = false;
                autocomplete.hideSuggestions();
                break;
            case "Backspace":
                // Check if this will make the search bar empty
                nextTick(() => {
                    if (!inputValue.value.trim()) {
                        // Search bar is now empty, hide suggestions
                        isContinuousSuggestionMode.value = false;
                        isAutocompleteIntentional.value = false;
                        autocomplete.hideSuggestions();
                    }
                });
                break;
            case "Tab":
                // Allow tab to accept suggestion if suggestions are visible and user didn't recently paste
                if (autocomplete.state.isVisible && !isRecentlyPasted.value) {
                    const tabSelected = autocomplete.getSelectedSuggestion();
                    if (tabSelected) {
                        event.preventDefault();
                        applySuggestion(tabSelected);
                        // End continuous mode after applying suggestion
                        isContinuousSuggestionMode.value = false;
                    }
                }
                break;
        }
    } else {
        // Handle regular input events when autocomplete is not visible
        switch (event.key) {
            case "Enter":
                // Always search when autocomplete is not active
                emit("enter");
                break;
            case " ":
                // Reset any lingering autocomplete state on space when not in suggestions
                isAutocompleteIntentional.value = false;
                isContinuousSuggestionMode.value = false;
                break;
        }
    }

    // Update cursor position after key events
    nextTick(() => {
        updateCursorPosition();
    });
};

const handleFocus = () => {
    emit("focus");
    showAutocompleteOnFocus.value = true;

    // Show suggestions on focus if search bar is empty (automatic suggestions)
    if (!inputValue.value.trim() && !isRecentlyPasted.value) {
        isAutocompleteIntentional.value = false; // Automatic suggestion on focus
        nextTick(() => {
            autocomplete.showSuggestions(inputValue.value, cursorPosition.value);
        });
    }
};

const handleBlur = () => {
    emit("blur");
    showAutocompleteOnFocus.value = false;

    // Delay hiding suggestions to allow for clicking on suggestions
    setTimeout(() => {
        if (!showAutocompleteOnFocus.value) {
            autocomplete.hideSuggestions();
        }
    }, 150);
};

const handleClick = () => {
    updateCursorPosition();

    // Show suggestions on click if search bar is empty (automatic suggestions)
    if (!inputValue.value.trim() && !isRecentlyPasted.value) {
        isAutocompleteIntentional.value = false; // Automatic suggestion on click
        autocomplete.showSuggestions(inputValue.value, cursorPosition.value);
    }

    // Also clear any recent paste flag if user clicks (they're actively interacting)
    if (isRecentlyPasted.value) {
        isRecentlyPasted.value = false;
    }
};

const handlePaste = (event: ClipboardEvent) => {
    // Get the pasted content to analyze it
    const pastedText = event.clipboardData?.getData("text") || "";

    // Set a temporary paste flag
    isRecentlyPasted.value = true;

    // Reset autocomplete state initially
    resetAutocompleteState();

    // Use a short delay to let the paste complete and analyze the content
    setTimeout(() => {
        updateCursorPosition();

        // Analyze if the pasted content could benefit from autocomplete
        const shouldShowSuggestions = shouldShowSuggestionsForPastedContent(pastedText, inputValue.value);

        if (shouldShowSuggestions) {
            // Show suggestions for potentially incomplete field names
            isAutocompleteIntentional.value = false; // Mark as automatic
            autocomplete.showSuggestions(inputValue.value, cursorPosition.value);
        } else {
            // Hide suggestions for complete/complex text
            autocomplete.hideSuggestions();
            autocomplete.setSelectedIndex(-1);
        }

        // Clear the paste flag after ensuring everything is stable
        setTimeout(() => {
            isRecentlyPasted.value = false;
        }, 200);
    }, 10); // Very short delay to let paste complete
};

/**
 * Determine if pasted content should trigger autocomplete suggestions
 */
const shouldShowSuggestionsForPastedContent = (pastedText: string, currentValue: string): boolean => {
    // If the input is empty or only whitespace, don't show suggestions
    if (!currentValue.trim()) {
        return false;
    }

    // If pasted text contains operators or complex syntax, likely complete - no suggestions
    const hasComplexSyntax = /[=!><:()""']/.test(pastedText);
    if (hasComplexSyntax) {
        return false;
    }

    // If pasted text contains numbers mixed with special chars, likely complete - no suggestions
    const hasComplexNumberPattern = /\d+.*[^\w\s-]/.test(pastedText);
    if (hasComplexNumberPattern) {
        return false;
    }

    // If pasted text is very long (>20 chars), likely complete - no suggestions
    if (pastedText.length > 20) {
        return false;
    }

    // If pasted text contains spaces, check if it looks like a complete phrase
    if (pastedText.includes(" ") && pastedText.split(" ").length > 2) {
        return false;
    }

    // If we get here, it's likely a short, simple string that could be a partial field name
    // Show suggestions for things like: "acc", "meta", "particle", etc.
    return true;
};

const triggerAutocomplete = () => {
    updateCursorPosition();
    isAutocompleteIntentional.value = true; // User intentionally triggered
    isContinuousSuggestionMode.value = true; // Enable continuous suggestion mode
    isRecentlyPasted.value = false; // Clear paste flag since user explicitly wants autocomplete
    autocomplete.showSuggestions(inputValue.value, cursorPosition.value);
};

const resetAutocompleteState = () => {
    isAutocompleteIntentional.value = false;
    isContinuousSuggestionMode.value = false;
    isRecentlyPasted.value = false; // Also reset paste flag
    autocomplete.hideSuggestions();
    // Also clear any selected suggestion to prevent stale selections
    autocomplete.setSelectedIndex(-1);
};

const handleSuggestionSelect = (suggestion: SuggestionItem) => {
    applySuggestion(suggestion);
};

const handleSuggestionHighlight = (index: number) => {
    if (index === -1) {
        autocomplete.hideSuggestions();
    } else {
        // Update selected index using the exposed method
        autocomplete.setSelectedIndex(index);
    }
};

const applySuggestion = (suggestion: SuggestionItem) => {
    const result = autocomplete.applySuggestion(inputValue.value, cursorPosition.value, suggestion);

    inputValue.value = result.newQuery;

    // Set cursor position after applying suggestion
    nextTick(() => {
        const input = inputElement.value;
        if (input) {
            input.focus();
            input.setSelectionRange(result.newCursorPosition, result.newCursorPosition);
            cursorPosition.value = result.newCursorPosition;
        }
    });

    autocomplete.hideSuggestions();
    // Reset flags after applying suggestion
    isAutocompleteIntentional.value = false;
    isContinuousSuggestionMode.value = false;
};

const handleClear = () => {
    inputValue.value = "";
    autocomplete.hideSuggestions();
    isAutocompleteIntentional.value = false;
    isContinuousSuggestionMode.value = false;
    isRecentlyPasted.value = false;

    // Focus the input after clearing
    nextTick(() => {
        const input = inputElement.value;
        if (input) {
            input.focus();
            cursorPosition.value = 0;
        }
    });
};

// Initialize field names on mount
onMounted(() => {
    autocomplete.loadFieldNames();
});

// Expose methods for parent components
defineExpose({
    focus: () => inputElement.value?.focus(),
    blur: () => inputElement.value?.blur(),
    triggerAutocomplete,
});
</script>
