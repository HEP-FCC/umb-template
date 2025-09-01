<template>
    <div
        v-if="suggestions.length > 0 && isVisible"
        ref="dropdownRef"
        class="absolute top-full left-0 right-0 z-50 mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-60 min-w-full flex flex-col"
    >
        <!-- Header with keyboard hints - always visible -->
        <div class="border-b border-primary-100 px-3 py-2 bg-gray-50 text-xs text-energy flex-shrink-0">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1 text-center sm:text-left">
                <div class="flex flex-wrap justify-center sm:justify-start gap-x-3 gap-y-1">
                    <span class="inline-flex items-center gap-1">
                        <kbd class="px-1 py-0.5 bg-white border border-gray-300 rounded text-xs">Ctrl+Space</kbd>
                        <span>show suggestions</span>
                    </span>
                    <span class="inline-flex items-center gap-1">
                        <kbd class="px-1 py-0.5 bg-white border border-gray-300 rounded text-xs">↑↓</kbd>
                        <span>navigate</span>
                    </span>
                </div>
                <div class="flex flex-wrap justify-center sm:justify-end gap-x-3 gap-y-1">
                    <span class="inline-flex items-center gap-1">
                        <kbd class="px-1 py-0.5 bg-white border border-gray-300 rounded text-xs">Enter/Tab</kbd>
                        <span>accept</span>
                    </span>
                    <span class="inline-flex items-center gap-1">
                        <kbd class="px-1 py-0.5 bg-white border border-gray-300 rounded text-xs">Esc</kbd>
                        <span>close</span>
                    </span>
                </div>
            </div>
        </div>

        <!-- Scrollable suggestions area -->
        <div class="py-1 overflow-y-auto scroll-smooth flex-1">
            <div
                v-for="(suggestion, index) in suggestions"
                :key="suggestion.value"
                :data-index="index"
                class="px-3 py-2 cursor-pointer text-sm flex items-center gap-2 hover:bg-blue-50 transition-colors"
                :class="{
                    'bg-blue-100 text-primary': index === selectedIndex,
                    'text-gray-900': index !== selectedIndex,
                }"
                @click="$emit('select', suggestion)"
                @mouseenter="$emit('highlight', index)"
            >
                <UIcon
                    :name="suggestion.type === 'field' ? 'i-heroicons-tag' : 'i-heroicons-adjustments-horizontal'"
                    class="w-4 h-4 flex-shrink-0"
                    :class="suggestion.type === 'field' ? 'text-primary' : 'text-eco'"
                />
                <span
                    class="font-mono flex-1 truncate min-w-0"
                    :class="suggestion.type === 'field' ? 'text-primary' : 'text-eco'"
                    :title="suggestion.value"
                    style="max-width: 200px"
                >
                    {{ suggestion.value }}
                </span>
                <span
                    v-if="suggestion.type === 'operator' && suggestion.description"
                    class="text-xs text-gray-500 ml-auto"
                >
                    {{ suggestion.description }}
                </span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
interface SuggestionItem {
    readonly value: string;
    readonly type: "field" | "operator" | "value";
    readonly description?: string;
}

interface Props {
    suggestions: readonly SuggestionItem[];
    isVisible: boolean;
    selectedIndex: number;
    inputElement: HTMLElement | null;
}

interface Emits {
    (e: "select", suggestion: SuggestionItem): void;
    (e: "highlight", index: number): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Refs
const dropdownRef = ref<HTMLElement | null>(null);

// Methods
const scrollToSelectedItem = () => {
    if (!dropdownRef.value || props.selectedIndex < 0) return;

    const selectedElement = dropdownRef.value.querySelector(`[data-index="${props.selectedIndex}"]`) as HTMLElement;
    const scrollContainer = dropdownRef.value;

    if (selectedElement && scrollContainer) {
        const containerRect = scrollContainer.getBoundingClientRect();
        const itemRect = selectedElement.getBoundingClientRect();

        // Check if item is outside the visible area
        const isAbove = itemRect.top < containerRect.top;
        const isBelow = itemRect.bottom > containerRect.bottom;

        if (isAbove || isBelow) {
            selectedElement.scrollIntoView({
                behavior: "smooth",
                block: "nearest",
            });
        }
    }
};

// Handle clicks outside to close dropdown
const handleClickOutside = (event: MouseEvent) => {
    if (
        props.isVisible &&
        dropdownRef.value &&
        !dropdownRef.value.contains(event.target as Node) &&
        props.inputElement &&
        !props.inputElement.contains(event.target as Node)
    ) {
        // Emit a close event instead of handling it here
        emit("highlight", -1);
    }
};

// Watchers
watch(
    () => props.selectedIndex,
    () => {
        if (props.isVisible && props.selectedIndex >= 0) {
            nextTick(() => {
                scrollToSelectedItem();
            });
        }
    },
);

// Lifecycle
onMounted(() => {
    document.addEventListener("click", handleClickOutside);
});

onUnmounted(() => {
    document.removeEventListener("click", handleClickOutside);
});
</script>
