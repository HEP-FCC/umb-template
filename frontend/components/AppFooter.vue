<template>
    <footer class="bg-space-50 mt-auto">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-center items-center h-6 text-xs">
                <span>© CERN {{ currentYear }}</span>
            </div>
        </div>
    </footer>
</template>

<script setup lang="ts">
const currentYear = new Date().getFullYear();
</script>
