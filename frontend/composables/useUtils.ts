import {
    formatFieldLabel,
    createEntityDownloadFilename,
    downloadAsJsonFile,
    formatFieldName,
    copyToClipboard,
    formatTimestamp,
    formatSizeInGiB,
    isStatusField,
    getStatusBadgeColor,
} from "~/utils/formatting";

import type { Entity } from "~/types/api";

/**
 * Get primary key value from entity
 */
export function getPrimaryKeyValue(entity: Entity): number | null {
    return entity.entity_id || null;
}

/**
 * Extract entity IDs from entity array
 */
export function extractEntityIds(entities: Entity[]): number[] {
    return entities.map((entity) => getPrimaryKeyValue(entity)).filter((id): id is number => id !== null);
}

/**
 * Retry function with exponential backoff
 */
export interface RetryOptions {
    maxAttempts?: number;
    baseDelay?: number;
    maxDelay?: number;
    backoffFactor?: number;
}

export async function retryWithBackoff<T>(operation: () => Promise<T>, options: RetryOptions = {}): Promise<T> {
    const { maxAttempts = 3, baseDelay = 1000, maxDelay = 10000, backoffFactor = 2 } = options;

    let lastError: Error;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return await operation();
        } catch (error) {
            lastError = error as Error;

            if (attempt === maxAttempts) {
                throw lastError;
            }

            const delay = Math.min(baseDelay * Math.pow(backoffFactor, attempt - 1), maxDelay);
            await new Promise((resolve) => setTimeout(resolve, delay));
        }
    }

    throw lastError!;
}

/**
 * Composable for utility functions
 * Provides reactive versions of utility functions and manages state
 */
export function useUtils() {
    // Re-export utility functions for convenience
    return {
        // Pure utility functions (re-exported from utils)
        formatFieldLabel,
        createEntityDownloadFilename,
        downloadAsJsonFile,
        formatFieldName,
        copyToClipboard,
        formatTimestamp,
        formatSizeInGiB,
        isStatusField,
        getStatusBadgeColor,

        // Entity utilities
        getPrimaryKeyValue,
        extractEntityIds,
        retryWithBackoff,
    };
}
