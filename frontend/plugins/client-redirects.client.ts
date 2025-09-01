/**
 * Client-side redirect plugin
 * Handles redirects that might be missed by server middleware
 * Runs only on client-side for SPA navigation
 */
export default defineNuxtPlugin({
    name: "client-redirects",
    setup() {
        const router = useRouter();
        const { checkAndRedirect } = useRedirects();

        // Handle client-side navigation redirects
        router.beforeEach(async (to) => {
            // Only run on client-side
            if (import.meta.server) {
                return;
            }

            const path = to.path;

            // Check if this path should be redirected
            const wasRedirected = await checkAndRedirect(path);

            if (wasRedirected) {
                // Navigation will be handled by the redirect
                return false;
            }
        });
    },
});
