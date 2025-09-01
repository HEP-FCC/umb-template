<template>
    <UContainer class="py-4 sm:py-6 lg:py-8">
        <EntitySearchInterface :initial-filters="activeFilters" :route-params="routeParams" />
    </UContainer>
</template>

<script setup lang="ts">
// Auto-imported: computed, ref, watchEffect, onMounted
// Auto-imported: useRoute
// Auto-imported: useDynamicNavigation, useAppConfiguration
import EntitySearchInterface from "~/components/search/EntitySearchInterface.vue";

const route = useRoute();
const { parseRouteToFilters, parseRouteToPath, getPageTitle } = useDynamicNavigation();
const appConfigComposable = useAppConfiguration();

const routeParams = computed(() => {
    return Array.isArray(route.params.slug) ? route.params.slug : route.params.slug ? [route.params.slug] : [];
});

// Computed filters and path from route params (synchronous)
const activeFilters = computed(() => {
    const params = routeParams.value;
    try {
        return parseRouteToFilters(params);
    } catch (error) {
        console.error("Error parsing route to filters:", error);
        return {};
    }
});

const currentPath = computed(() => {
    const params = routeParams.value;
    try {
        return parseRouteToPath(params);
    } catch (error) {
        console.error("Error parsing route to path:", error);
        return {};
    }
});

// Computed properties for page meta
const pageTitle = computed(() => {
    const path = currentPath.value;
    try {
        return Object.keys(path).some((key) => path[key]) ? getPageTitle(path) : appConfigComposable.appTitle.value;
    } catch (error) {
        console.error("Error getting page title:", error);
        return appConfigComposable.appTitle.value;
    }
});

const pageDescription = computed(() => {
    return appConfigComposable.searchDescription.value(activeFilters.value);
});

// Load app configuration on mount
onMounted(async () => {
    await appConfigComposable.loadAppConfig();
});

// Set the page title and meta
useHead({
    title: pageTitle,
    meta: [
        {
            name: "description",
            content: pageDescription,
        },
        {
            property: "og:title",
            content: pageTitle,
        },
        {
            property: "og:description",
            content: pageDescription,
        },
    ],
});
</script>
