import type { RedirectConfig } from "~/types/schema";

/**
 * Global route middleware to handle legacy URL redirects
 * This runs before any page component is rendered
 */
export default defineNuxtRouteMiddleware(async (to) => {
    // Only run on client-side since we're in CSR mode
    if (import.meta.server) {
        return;
    }

    try {
        // Load redirect configuration
        const config = (await $fetch("/api/_redirects")) as RedirectConfig;
        const redirectTarget = config.redirects[to.path];

        if (redirectTarget) {
            // Handle empty redirect target (remove page)
            if (redirectTarget === "") {
                console.log(`Redirecting ${to.path} to home page (empty target)`);
                return navigateTo("/", { redirectCode: 301, replace: true });
            }

            // Preserve query parameters if they exist
            const targetUrl = to.fullPath.includes("?")
                ? `${redirectTarget}${to.fullPath.slice(to.path.length)}`
                : redirectTarget;

            console.log(`Redirecting ${to.path} to ${targetUrl}`);
            return navigateTo(targetUrl, { redirectCode: 301, replace: true });
        }
    } catch (error) {
        console.warn("Failed to check redirects:", error);
    }

    // No redirect needed, continue normally
});
