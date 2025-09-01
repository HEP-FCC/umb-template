/**
 * TypeScript types for comexport interface SearchComposable {
    // State
    userSearchQuery: Ref<string>;
    infiniteScrollEnabled: Ref<boolean>;
    activeFilters: Ref<Record<string, string>>;
    entities: Ref<Entity[]>;
    searchState: SearchState;
    scrollState: ScrollState;
    sortState: SortState;
    apiAvailable: ComputedRef<boolean>; Defines interfaces for reactive state and composable returns
 */

import type { Ref, ComputedRef } from "vue";
import type { Entity, ApiError, DropdownOption } from "./api";
import type { SearchState, ScrollState, SortState } from "./entity";

/**
 * State interfaces for composables
 */
export interface AsyncState<T> {
    data: Ref<T | null>;
    loading: Ref<boolean>;
    error: Ref<ApiError | null>;
    refresh: () => Promise<void>;
}

export interface SelectionState {
    selectedIds: Set<number>;
    selectedEntities: Set<number>;
    expandedMetadata: Set<number>;
    selectAll: boolean;
    isIndeterminate: boolean;
    isDownloading: boolean;
}

/**
 * Composable return types
 */
export interface EntitySearchComposable {
    // State
    userSearchQuery: Ref<string>;
    infiniteScrollEnabled: Ref<boolean>;
    activeFilters: Ref<Record<string, string>>;
    isFilterUpdateInProgress: Ref<boolean>;
    entities: Ref<Entity[]>;
    searchState: SearchState;
    scrollState: ScrollState;
    sortState: SortState;
    apiAvailable: Ref<boolean>;

    // Computed
    urlFilterQuery: ComputedRef<Record<string, string>>;
    combinedSearchQuery: ComputedRef<string>;
    searchPlaceholderText: ComputedRef<string>;
    showFilterNote: ComputedRef<boolean>;
    canCopyLink: ComputedRef<boolean>;
    currentDisplayRange: ComputedRef<{ start: number; end: number; total: number }>;
    canLoadMore: ComputedRef<boolean>;
    sortingFieldOptions: ComputedRef<Array<{ label: string; value: string }>>;
    showLoadingSkeleton: ComputedRef<boolean>;
    shouldShowLoadingIndicatorEntities: ComputedRef<boolean>;
    shouldShowCompletionMessage: ComputedRef<boolean>;

    // Methods
    performSearch: (isInitialLoad?: boolean) => Promise<void>;
    fetchSortingFields: () => Promise<void>;
    executeSearch: (pageToLoad?: number, isInitialLoad?: boolean) => Promise<void>;
    handleSearch: () => Promise<void>;
    loadMoreData: () => Promise<void>;
    toggleMode: () => void;
    toggleSortOrder: () => void;
    handlePageSizeChange: (newSize: number) => void;
    updateFilters: (filters: Record<string, string>) => Promise<void>;
    initializeSearch: () => Promise<void>;
    updateCurrentPage: (page: number) => void;
    updatePageSize: (size: number) => void;
    updateSortBy: (field: string) => Promise<void>;
    clearError: () => void;
    updateEntity: (index: number, entity: Entity) => void;
    cleanup: () => void;
}

export interface NavigationConfigComposable {
    navigationConfig: Ref<Record<string, DropdownOption[]>>;
    isLoading: Ref<boolean>;
    error: Ref<string | null>;
    fetchNavigationConfig: () => Promise<void>;
    getDropdownOptions: (type: string) => DropdownOption[];
    refreshNavigationConfig: () => Promise<void>;
}

/**
 * Common types used across composables
 */
export type SortOrder = "asc" | "desc";

export interface FilterOptions {
    [key: string]: string | number | boolean | null;
}

export interface SearchOptions {
    query?: string;
    filters?: FilterOptions;
    sortBy?: string;
    sortOrder?: SortOrder;
    page?: number;
    pageSize?: number;
}

/**
 * Error handling types
 */
export interface ComposableError extends Error {
    status?: number;
    context?: string;
    retryable?: boolean;
}

export interface RetryOptions {
    maxAttempts?: number;
    delay?: number;
    backoffMultiplier?: number;
    retryCondition?: (error: Error) => boolean;
}
