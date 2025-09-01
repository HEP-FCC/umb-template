/**
 * API endpoint to serve redirect configuration
 * GET /api/_redirects
 */
export default defineEventHandler(async (_event) => {
    try {
        // Try to import the redirects config directly
        // This works in both dev and production as the config gets bundled
        const config = await import("~/config/redirects.json");

        return config.default || config;
    } catch (error) {
        console.error("Failed to load redirect configuration:", error);

        // Return empty configuration on error
        return {
            redirects: {},
        };
    }
});
