let cachedSchema: Record<string, unknown> | null = null;
let schemaPromise: Promise<Record<string, unknown>> | null = null;

/**
 * Composable for managing API schema with caching
 * Ensures schema is only fetched once and reused across the application
 */
export const useSchema = () => {
    const { getSchemaConfig } = useApiClient();

    const getSchema = async (): Promise<Record<string, unknown>> => {
        // If we already have the schema cached, return it immediately
        if (cachedSchema) {
            return cachedSchema;
        }

        // If a request is already in progress, return the same promise
        if (schemaPromise) {
            return schemaPromise;
        }

        // Create new request and cache the promise
        schemaPromise = getSchemaConfig();

        try {
            const schema = await schemaPromise;
            cachedSchema = schema;
            return schema;
        } catch (error) {
            // Reset promise on error so we can retry
            schemaPromise = null;
            throw error;
        } finally {
            // Clear the promise reference once resolved/rejected
            schemaPromise = null;
        }
    };

    const clearCache = () => {
        cachedSchema = null;
        schemaPromise = null;
    };

    const isLoaded = () => cachedSchema !== null;

    return {
        getSchema,
        clearCache,
        isLoaded,
    };
};
