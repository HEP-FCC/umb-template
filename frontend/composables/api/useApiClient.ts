/**
 * Typed API client using Nuxt 3's $fetch with automatic token refresh
 * Provides type-safe API calls with proper error handling and automatic token renewal
 */

import type {
    Entity,
    SearchApiResponse,
    ApiError,
    TypedFetchOptions,
    CreateEntityPayload,
    UpdateEntityPayload,
} from "~/types/api";
import type { SearchOptions } from "~/types/composables";

// Global state for tracking refresh operations to prevent concurrent refreshes
let isRefreshing = false;
let refreshPromise: Promise<boolean> | null = null;

/**
 * Composable for typed API client with automatic token refresh
 */
export function useApiClient() {
    const config = useRuntimeConfig();
    const baseUrl = config.public.apiBaseUrl || "http://localhost:8000";

    /**
     * Attempt to refresh the access token using the refresh token endpoint
     */
    const refreshToken = async (): Promise<boolean> => {
        // Prevent concurrent refresh attempts
        if (isRefreshing && refreshPromise) {
            return await refreshPromise;
        }

        isRefreshing = true;
        refreshPromise = (async (): Promise<boolean> => {
            try {
                console.log("Attempting to refresh access token...");

                const response = await $fetch<{
                    status: string;
                    message: string;
                    expires_in: number;
                }>(`${baseUrl}/refresh-auth-token`, {
                    method: "POST",
                    credentials: "include",
                    headers: {
                        "Content-Type": "application/json",
                    },
                });

                if (response.status === "success") {
                    console.log("Token refresh successful");
                    return true;
                } else {
                    console.warn("Token refresh failed:", response.message);
                    return false;
                }
            } catch (error: unknown) {
                console.error("Token refresh failed:", error);

                // Check if it's a 401 error indicating refresh token is also expired
                if (error && typeof error === "object" && ("status" in error || "statusCode" in error)) {
                    const statusError = error as { status?: number; statusCode?: number };
                    if (statusError.status === 401 || statusError.statusCode === 401) {
                        console.log("Refresh token expired, redirecting to login...");
                        // Clear any existing auth state and redirect to login
                        await navigateTo(`${baseUrl}/login`);
                    }
                }

                return false;
            } finally {
                isRefreshing = false;
                refreshPromise = null;
            }
        })();

        return await refreshPromise;
    };

    /**
     * Enhanced fetch wrapper with automatic token refresh on 401 errors
     */
    const typedFetch = async <T>(endpoint: string, options: TypedFetchOptions = {}): Promise<T> => {
        const executeRequest = async (isRetry = false): Promise<T> => {
            try {
                let fullUrl = `${baseUrl}${endpoint}`;

                // Manually construct query string to avoid any $fetch issues
                if (options.query && Object.keys(options.query).length > 0) {
                    const queryParams = new URLSearchParams();
                    for (const [key, value] of Object.entries(options.query)) {
                        if (value !== undefined && value !== null) {
                            queryParams.append(key, String(value));
                        }
                    }
                    fullUrl += `?${queryParams.toString()}`;
                }

                const response = await $fetch<T>(fullUrl, {
                    method: (options.method || "GET") as "GET" | "POST" | "PUT" | "DELETE",
                    body: options.body as Record<string, unknown> | undefined,
                    headers: {
                        "Content-Type": "application/json",
                        ...options.headers,
                    },
                    credentials: "include",
                });

                return response;
            } catch (error: unknown) {
                const errorObj = error as Record<string, unknown>;
                const status = (errorObj.statusCode as number) || (errorObj.status as number) || 500;

                // Handle 401 Unauthorized errors with automatic token refresh
                if (status === 401 && !isRetry) {
                    console.log("Received 401 error, attempting token refresh...");

                    const refreshSuccess = await refreshToken();
                    if (refreshSuccess) {
                        console.log("Token refreshed successfully, retrying original request...");
                        // Retry the original request with the new token
                        return executeRequest(true);
                    } else {
                        console.log("Token refresh failed, throwing original error");
                        // Token refresh failed, throw the original error
                    }
                }

                console.error(`API Error for ${endpoint}:`, error);

                // Determine error type for better error handling
                const isNetworkError =
                    error instanceof TypeError ||
                    errorObj?.name === "NetworkError" ||
                    errorObj?.code === "NETWORK_ERROR" ||
                    navigator.onLine === false;

                const isServerError = status >= 500 && status < 600;
                const isAuthError = status === 401 || status === 403;

                const apiError: ApiError = {
                    message: (errorObj.message as string) || "API request failed",
                    status,
                    details: {
                        ...((errorObj.data as Record<string, unknown>) || {}),
                        error_type: isNetworkError
                            ? "network_error"
                            : isServerError
                            ? "server_error"
                            : isAuthError
                            ? "authentication_error"
                            : "api_error",
                    },
                };
                throw apiError;
            }
        };

        return executeRequest();
    };

    /**
     * Search entities with typed response - uses /query/ endpoint
     */
    const searchEntities = async (options: SearchOptions = {}): Promise<SearchApiResponse<Entity>> => {
        const queryParams: Record<string, string | number | boolean> = {};

        if (options.query) queryParams.q = options.query;
        if (options.pageSize) queryParams.limit = options.pageSize;
        if (options.page && options.pageSize) {
            queryParams.offset = (options.page - 1) * options.pageSize;
        }
        if (options.sortBy) queryParams.sort_by = options.sortBy;
        if (options.sortOrder) queryParams.sort_order = options.sortOrder;

        const backendResponse = await typedFetch<{ total: number; items: Entity[] }>("/query/", {
            method: "GET",
            query: queryParams,
        });

        // Transform backend response to match frontend interface
        const result: SearchApiResponse<Entity> = {
            data: backendResponse.items,
            total: backendResponse.total,
            success: true,
            query: options.query,
            filters: options.filters,
            sortBy: options.sortBy,
            sortOrder: options.sortOrder,
        };

        return result;
    };
    /**
     * Get entity by ID
     */
    const getEntityById = async (id: number): Promise<Entity> => {
        // Add cache-busting timestamp to ensure fresh data
        const timestamp = Date.now();
        return typedFetch<Entity>(`/entities/${id}?_t=${timestamp}`);
    };

    /**
     * Get multiple entities by IDs
     */
    const getEntitiesByIds = async (ids: number[]): Promise<Entity[]> => {
        return typedFetch<Entity[]>("/entities/", {
            method: "POST",
            body: { entity_ids: ids },
        });
    };

    /**
     * Create new entity
     */
    const createEntity = async (payload: CreateEntityPayload): Promise<Entity> => {
        return typedFetch<Entity>("/entities", {
            method: "POST",
            body: payload,
        });
    };

    /**
     * Update entity
     */
    const updateEntity = async (id: number, payload: UpdateEntityPayload): Promise<Entity> => {
        return typedFetch<Entity>(`/entities/${id}`, {
            method: "PUT",
            body: payload,
        });
    };

    /**
     * Update entity metadata lock state
     */
    const updateMetadataLock = async (
        entityId: number,
        fieldName: string,
        locked: boolean,
    ): Promise<{ success: boolean; message: string }> => {
        return typedFetch<{ success: boolean; message: string }>(`/entities/${entityId}/metadata/lock`, {
            method: "PUT",
            body: { field_name: fieldName, locked },
        });
    };

    /**
     * Delete entity
     */
    const deleteEntity = async (id: number): Promise<undefined> => {
        return typedFetch<undefined>(`/entities/${id}`, {
            method: "DELETE",
        });
    };

    /**
     * Delete multiple entities by their IDs
     */
    const deleteEntities = async (
        entityIds: number[],
    ): Promise<{
        success: boolean;
        deleted_count: number;
        not_found_count: number;
        message: string;
        deleted_ids?: number[];
        not_found_ids?: number[];
    }> => {
        return typedFetch<{
            success: boolean;
            deleted_count: number;
            not_found_count: number;
            message: string;
            deleted_ids?: number[];
            not_found_ids?: number[];
        }>("/entities/", {
            method: "DELETE",
            body: JSON.stringify({ entity_ids: entityIds }),
        });
    };

    /**
     * Get sorting fields
     */
    const getSortingFields = async (): Promise<{ fields: string[]; count: number; info: string }> => {
        return typedFetch<{ fields: string[]; count: number; info: string }>("/sorting-fields/");
    };

    /**
     * Get dropdown options for navigation
     */
    const getDropdownOptions = async (type: string): Promise<Array<{ entity_id: number; name: string }>> => {
        const response = await typedFetch<{ data: Array<{ entity_id: number; name: string }> }>(`/dropdown/${type}`);
        return response.data;
    };

    /**
     * Get schema configuration
     */
    const getSchemaConfig = async (): Promise<Record<string, unknown>> => {
        return typedFetch<Record<string, unknown>>("/schema");
    };

    /**
     * Download entities as JSON - same as getEntitiesByIds
     */
    const downloadEntitiesByIds = async (ids: number[]): Promise<Entity[]> => {
        return getEntitiesByIds(ids);
    };

    /**
     * Download all filtered entities based on search query
     */
    const downloadFilteredEntities = async (options: SearchOptions = {}): Promise<Entity[]> => {
        const queryParams: Record<string, string | number | boolean> = {};

        if (options.query) queryParams.q = options.query;
        if (options.sortBy) queryParams.sort_by = options.sortBy;
        if (options.sortOrder) queryParams.sort_order = options.sortOrder;

        return typedFetch<Entity[]>("/download-filtered/", {
            method: "GET",
            query: queryParams,
        });
    };

    /**
     * Initiate OAuth login - redirects user to authentication
     */
    const initiateLogin = (): void => {
        window.location.href = `${baseUrl}/login`;
    };

    /**
     * Logout user and get logout URL
     */
    const logoutUser = async (): Promise<{ logout_url: string }> => {
        return typedFetch<{ logout_url: string }>("/logout", {
            method: "GET",
        });
    };

    /**
     * Get session authentication status
     */
    const getSessionStatus = async (): Promise<{ authenticated: boolean; user?: Record<string, unknown> }> => {
        return typedFetch<{ authenticated: boolean; user?: Record<string, unknown> }>("/session-status", {
            method: "GET",
        });
    };

    /**
     * Manually refresh authentication tokens
     * Useful for proactive token refresh or manual retry scenarios
     */
    const manualRefreshToken = async (): Promise<boolean> => {
        return refreshToken();
    };

    /**
     * Generic GET method using the enhanced typedFetch with automatic token refresh
     */
    const apiGet = async <T>(url: string, query?: Record<string, string | number | boolean>): Promise<T> => {
        return typedFetch<T>(url, {
            method: "GET",
            query,
        });
    };

    return {
        // Core methods
        typedFetch,
        apiGet,

        // Entity operations
        searchEntities,
        getEntityById,
        getEntitiesByIds,
        createEntity,
        updateEntity,
        updateMetadataLock,
        deleteEntity,
        deleteEntities,

        // Utility methods
        getSortingFields,
        getDropdownOptions,
        getSchemaConfig,
        downloadEntitiesByIds,
        downloadFilteredEntities,

        // Authentication methods
        initiateLogin,
        logoutUser,
        getSessionStatus,
        manualRefreshToken,

        // Configuration
        baseUrl,
    };
}
