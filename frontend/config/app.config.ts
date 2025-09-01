/**
 * Application Configuration
 *
 * This is the ONLY file that needs to be modified to adapt the frontend to different data schemas.
 * The system will auto-discover the database schema and generate navigation based on this config
 * combined with the actual database foreign key relationships.
 */

/**
 * Core application settings - modify these for different deployments
 */
export const APP_CONFIG = {
    /**
     * The main entity table name (source of truth for all data)
     * This table should contain foreign keys to all navigation entities
     */
    mainTable: "entities" as const,

    /**
     * Application branding and metadata
     */
    branding: {
        title: "Universal Metadata Browser",
        appTitle: "Universal Metadata Browser",
        description: "Search and explore your metadata catalog",
        defaultTitle: "Metadata Search",
    },

    /**
     * API configuration
     */
    api: {
        baseUrl: process.env.NUXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
        timeout: 30000,
    },

    /**
     * Authentication configuration
     */
    auth: {
        enabled: process.env.NUXT_PUBLIC_AUTH_ENABLED !== "false",
        loginUrl: "/login",
        logoutUrl: "/logout",
        sessionStatusUrl: "/session-status",
        refreshTokenUrl: "/refresh-auth-token",
    },

    /**
     * Navigation order - will be fetched dynamically from backend
     * This is just a placeholder for type safety
     */
    navigationOrder: [] as readonly string[],

    /**
     * Navigation configuration - will be fetched dynamically from backend
     * This is just a placeholder structure for type safety
     */
    navigationMenu: {} as Record<
        string,
        {
            icon: string;
            label: string;
            description: string;
        }
    >,

    /**
     * Search and infinite scroll settings
     */
    search: {
        defaultPageSize: 25,
        maxPageSize: 1000,
    },

    /**
     * UI configuration
     */
    ui: {
        defaultBadgeColors: ["energy"] as const,
        // Use folder icon for all navigation items
        defaultIcon: "i-heroicons-folder" as const,
    },

    /**
     * Metadata preferences configuration
     */
    metadata: {
        // Default metadata fields to display as badges/tags - customize for your domain
        defaultSelectedFields: ["title", "description", "status"] as const,
    },

    /**
     * File download configuration
     */
    downloads: {
        // Prefix for downloaded file names
        fileNamePrefix: "metadata_entities" as const,
    },

    /**
     * Cookie configuration
     */
    cookies: {
        // Prefix for all cookie names used by the application
        namePrefix: "metadata" as const,
    },

    /**
     * Navigation configuration fallbacks
     * Used when backend navigation config is not available
     */
    navigationFallback: {
        // Common navigation types in expected order - customize for your domain
        order: ["category", "type", "source", "status", "format"] as const,
    },
} as const;

/**
 * Type definitions derived from config
 */
export type MainTableType = typeof APP_CONFIG.mainTable;

/**
 * Type for navigation keys that will be dynamically determined
 */
export type NavigationKey = string;
export type BadgeColor =
    | (typeof APP_CONFIG.ui.defaultBadgeColors)[number]
    | "primary"
    | "neutral"
    | "success"
    | "warning"
    | "info"
    | "error"
    | "eco"
    | "earth"
    | "radiant-blue"
    | "space"
    | "flash"
    | "energy"
    | "deep-blue";
