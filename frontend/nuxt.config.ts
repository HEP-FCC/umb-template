export default defineNuxtConfig({
    compatibilityDate: "2025-05-15",

    // Enable CSR mode for better search application performance
    ssr: false,

    colorMode: {
        preference: "light",
        fallback: "light",
        dataValue: "light",
        classSuffix: "",
        storageKey: "nuxt-color-mode",
    },

    modules: ["@nuxt/eslint", "@nuxt/fonts", "@nuxt/icon", "@nuxt/image", "@nuxt/scripts", "@nuxt/ui"],
    css: ["assets/css/main.css"],

    // Nuxt UI Configuration - Register custom colors
    ui: {
        theme: {
            colors: [
                "primary",
                "secondary",
                "success",
                "info",
                "warning",
                "error",
                "neutral",
                // Your custom colors
                "eco",
                "earth",
                "radiant-blue",
                "space",
                "flash",
                "energy",
                "deep-blue",
                // Status-specific colors for badges
                "status-completed",
                "status-in-progress",
                "status-failed",
                "status-active",
                "status-neutral",
            ],
        },
    },

    // Ensure components in subdirectories are auto-imported
    components: [
        {
            path: "~/components",
            pathPrefix: false,
        },
    ],

    // Enhanced auto-imports for composables and utilities
    imports: {
        dirs: ["composables/**", "utils/**", "config/**"],
        presets: [
            {
                from: "vue-router",
                imports: ["RouteLocationNormalized", "Router"],
            },
            {
                from: "@vueuse/core",
                imports: ["watchDebounced", "useInfiniteScroll"],
            },
        ],
    },

    runtimeConfig: {
        public: {
            apiBaseUrl: process.env.METADATA_BROWSER_BACKEND_URL || "http://localhost:8000",
        },
    },

    // Fix for module resolution issues
    vite: {
        optimizeDeps: {
            exclude: ["@nuxt/kit"],
        },
    },

    // Performance optimizations for CSR
    experimental: {
        payloadExtraction: false,
    },

    // App configuration
    app: {
        head: {
            viewport: "width=device-width,initial-scale=1",
            charset: "utf-8",
        },
    },
});
