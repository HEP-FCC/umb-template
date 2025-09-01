import type { RedirectConfig } from "~/types/schema";

/**
 * Composable for managing URL redirects
 * Provides utilities for handling client-side redirects and redirect management
 */
export const useRedirects = () => {
    /**
     * Load redirect configuration (client-side)
     */
    const loadRedirectConfig = async (): Promise<Record<string, string>> => {
        try {
            // In production, this would be served as a static asset
            const response = (await $fetch("/api/_redirects")) as RedirectConfig;
            return response.redirects || {};
        } catch (error) {
            console.warn("Failed to load redirect configuration:", error);
            return {};
        }
    };

    /**
     * Check if a path should be redirected and perform the redirect
     */
    const checkAndRedirect = async (path: string): Promise<boolean> => {
        const config = await loadRedirectConfig();
        const redirectTarget = config[path];

        if (redirectTarget) {
            await navigateTo(redirectTarget, {
                redirectCode: 301,
                replace: true,
            });
            return true;
        }

        return false;
    };

    /**
     * Manually trigger a redirect based on configuration
     */
    const redirectTo = async (fromPath: string): Promise<void> => {
        const config = await loadRedirectConfig();
        const targetPath = config[fromPath];

        if (targetPath) {
            await navigateTo(targetPath, {
                redirectCode: 301,
                replace: true,
            });
        } else {
            console.warn(`No redirect configured for path: ${fromPath}`);
        }
    };

    return {
        loadRedirectConfig,
        checkAndRedirect,
        redirectTo,
    };
};
