/**
 * Modern API types for entity system
 * Compatible with the dynamic backend architecture
 */

/**
 * Standard HTTP status codes for API responses
 */
export enum HttpStatusCode {
    OK = 200,
    CREATED = 201,
    BAD_REQUEST = 400,
    UNAUTHORIZED = 401,
    FORBIDDEN = 403,
    NOT_FOUND = 404,
    INTERNAL_SERVER_ERROR = 500,
}

/**
 * API Error response structure
 */
export interface ApiError {
    message: string;
    status: HttpStatusCode;
    details?: {
        error?: string;
        message?: string;
        error_type?: "network_error" | "server_error" | "authentication_error" | "api_error";
        [key: string]: unknown;
    };
    timestamp?: string;
}

/**
 * Extended error structure that handles different API error formats
 * Used for error handling in composables where error structure may vary
 */
export interface ExtendedApiError {
    message?: string;
    details?: {
        detail?: {
            message?: string;
        };
        message?: string;
        user_message?: string;
        [key: string]: unknown;
    };
    data?: {
        detail?: {
            message?: string;
        };
        message?: string;
        user_message?: string;
        details?: {
            message?: string;
        };
        [key: string]: unknown;
    };
    [key: string]: unknown;
}

/**
 * Entity from the backend (replaces hardcoded models)
 */
export interface Entity {
    entity_id: number;
    uuid?: string;
    name: string;
    created_at?: string;
    updated_at?: string;
    last_edited_at?: string;
    edited_by_name?: string;
    metadata?: Record<string, unknown>;
    [key: string]: unknown; // Allow any additional fields from dynamic schema
}

/**
 * Entity with populated relationship details
 */
export interface EntityWithDetails extends Entity {
    // Relationship fields will be dynamically populated based on schema
    [relationshipField: string]: unknown;
}

/**
 * Generic API response wrapper
 */
export interface ApiResponse<T = unknown> {
    data?: T;
    message?: string;
    error?: ApiError;
    success: boolean;
}

/**
 * Simplified response for infinite scroll
 */
export interface InfiniteScrollApiResponse<T = Entity> {
    data: T[];
    total: number;
    success: boolean;
}

/**
 * Search API response structure
 */
export interface SearchApiResponse<T = Entity> extends InfiniteScrollApiResponse<T> {
    query?: string;
    filters?: Record<string, unknown>;
    sortBy?: string;
    sortOrder?: "asc" | "desc";
}

/**
 * Utility types for API operations
 */
export type CreateEntityPayload = Omit<Entity, "entity_id" | "created_at" | "last_edited_at">;
export type UpdateEntityPayload = Partial<Omit<Entity, "entity_id" | "created_at">> & { entity_id: number };

/**
 * API endpoint configuration
 */
export interface ApiEndpoint {
    method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
    path: string;
    authenticated?: boolean;
}

/**
 * Typed fetch options for better type safety
 */
export interface TypedFetchOptions<T = unknown> {
    method?: string;
    body?: T;
    headers?: Record<string, string>;
    query?: Record<string, string | number | boolean>;
}

/**
 * Navigation dropdown option
 */
export interface DropdownOption {
    value: string | number;
    label: string;
    count?: number;
}

/**
 * Dynamic navigation configuration from backend
 */
export interface NavigationConfig {
    type: "dropdown" | "search" | "toggle";
    label: string;
    column: string;
    options?: DropdownOption[];
    placeholder?: string;
}

/**
 * Entity creation/update payload
 */
export interface EntityPayload {
    name: string;
    metadata?: Record<string, unknown>;
    [key: string]: unknown; // Dynamic fields based on schema
}

/**
 * Search and filter types
 */
export interface SearchParams {
    q?: string; // Search query
    page?: number;
    pageSize?: number;
    sortBy?: string;
    sortOrder?: "asc" | "desc";
    [filterKey: string]: unknown; // Dynamic filters
}

/**
 * Sort configuration
 */
export interface SortConfig {
    field: string;
    order: "asc" | "desc";
    label?: string;
}

/**
 * Filter configuration for dynamic entity types
 */
export interface FilterConfig {
    key: string;
    label: string;
    type: "select" | "text" | "date" | "number";
    options?: Array<{ id: number | string; name: string }>;
    placeholder?: string;
}

/**
 * Entity selection state
 */
export interface SelectionState {
    selectedIds: Set<number>;
    selectedEntities: Set<number>;
    expandedMetadata: Set<number>;
    selectAll: boolean;
    isIndeterminate: boolean;
    isDownloading: boolean;
}

/**
 * Entity metadata editing state
 */
export interface MetadataEditState {
    isEditing: boolean;
    editingEntityId: number | null;
    editingData: Record<string, unknown>;
    hasChanges: boolean;
    json: string;
    editedJson: string;
    originalMetadata?: Record<string, unknown>;
    isSaving?: boolean;
}

/**
 * Application state for entity management
 */
export interface EntityManagementState {
    entities: Entity[];
    loading: boolean;
    error: string | null;
    selection: SelectionState;
    metadata: MetadataEditState;
    totalCount: number;
    currentPage: number;
    pageSize: number;
}

/**
 * Bulk operation result
 */
export interface BulkOperationResult {
    success: boolean;
    successCount: number;
    failureCount: number;
    errors?: string[];
    message: string;
    data?: unknown;
    error?: string;
}

// Export Entity as primary interface
