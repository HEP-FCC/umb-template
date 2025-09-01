import { readFileSync } from "fs";
import { join } from "path";

interface RedirectConfig {
    redirects: Record<string, string>;
}

let redirectConfig: RedirectConfig | null = null;

/**
 * Load redirect configuration from JSON file
 */
function loadRedirectConfig(): RedirectConfig {
    if (redirectConfig) {
        return redirectConfig;
    }

    try {
        const configPath = join(process.cwd(), "config", "redirects.json");
        const configContent = readFileSync(configPath, "utf-8");
        redirectConfig = JSON.parse(configContent) as RedirectConfig;
        return redirectConfig;
    } catch (error) {
        console.warn("Failed to load redirect configuration:", error);
        return { redirects: {} };
    }
}

/**
 * Server middleware to handle URL redirects
 * This runs before the Nuxt app and handles old URL patterns
 * Primarily for direct URL access (not SPA navigation)
 */
export default defineEventHandler(async (event) => {
    // Only handle GET requests for HTML pages
    if (event.method !== "GET") {
        return;
    }

    const url = getRequestURL(event);
    const pathname = url.pathname;

    // Skip API routes, assets, and other non-page requests
    if (
        pathname.startsWith("/api/") ||
        pathname.startsWith("/_nuxt/") ||
        pathname.startsWith("/favicon.ico") ||
        pathname.includes(".") ||
        pathname === "/" // Don't redirect home page
    ) {
        return;
    }

    // Load redirect configuration
    const config = loadRedirectConfig();

    // Check if we have a redirect rule for this path
    const redirectTarget = config.redirects[pathname];

    if (redirectTarget !== undefined) {
        // Handle empty redirect target (redirect to home)
        if (redirectTarget === "") {
            console.log(`Server redirect: ${pathname} -> / (empty target)`);
            await sendRedirect(event, "/", 301);
            return;
        }

        // Preserve query parameters from the original URL
        const searchParams = url.searchParams.toString();
        const targetUrl = searchParams ? `${redirectTarget}?${searchParams}` : redirectTarget;

        console.log(`Server redirect: ${pathname} -> ${targetUrl}`);

        // Send 301 permanent redirect
        await sendRedirect(event, targetUrl, 301);
        return;
    }

    // No redirect needed, continue with normal processing
});
