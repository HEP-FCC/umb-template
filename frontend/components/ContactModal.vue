<template>
    <UModal
        v-model:open="isOpen"
        title="Contact & Resources"
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
            icon="i-heroicons-envelope"
            color="neutral"
            variant="ghost"
            :label="iconOnly ? undefined : 'Contact'"
            @click="isOpen = true"
        />

        <template #body>
            <div class="space-y-6">
                <!-- Mailing List -->
                <div class="space-y-2">
                    <h3 class="text-sm font-medium text-deep-blue-900">Email Support</h3>
                    <div class="flex items-center space-x-2">
                        <UIcon name="i-heroicons-envelope" class="text-secondary-500" />
                        <a
                            href="mailto:admin@your-domain.com"
                            class="text-deep-blue-600 hover:text-deep-blue-900 transition-colors"
                        >
                            admin@your-domain.com
                        </a>
                    </div>
                </div>

                <!-- Support Forum -->
                <div class="space-y-2">
                    <h3 class="text-sm font-medium text-deep-blue-900">Support Forum</h3>
                    <div class="flex items-center space-x-2">
                        <UIcon name="i-heroicons-chat-bubble-left-right" class="text-secondary-500" />
                        <a
                            href="https://github.com/your-org/universal-metadata-browser/discussions"
                            target="_blank"
                            rel="noopener noreferrer"
                            class="text-deep-blue-600 hover:text-deep-blue-900 transition-colors"
                        >
                            Visit Forum
                        </a>
                    </div>
                </div>

                <!-- GitHub Source -->
                <div class="space-y-2">
                    <h3 class="text-sm font-medium text-deep-blue-900">Source Code</h3>
                    <div class="flex items-center space-x-2">
                        <UIcon name="i-heroicons-code-bracket" class="text-secondary-500" />
                        <a
                            href="https://github.com/your-org/universal-metadata-browser"
                            target="_blank"
                            rel="noopener noreferrer"
                            class="text-deep-blue-600 hover:text-deep-blue-900 transition-colors"
                        >
                            GitHub Repository
                        </a>
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
</script>
