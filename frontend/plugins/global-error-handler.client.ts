/**
 * Global Error Handler Plugin for Nuxt
 * Centralized error handling for all application errors with user-friendly notifications
 */

import type { ComponentPublicInstance } from "vue";

// Extended API Error interface for error handling (more flexible than types/api.ts)
interface UnifiedApiError {
    message: string;
    status: number;
    details?: {
        error?: string;
        message?: string;
        type?: string;
        code?: string;
        required_role?: string;
        validation_errors?: Record<string, string[]>;
    };
    statusCode?: number;
    data?: Record<string, unknown>;
    headers?: Record<string, string>;
}

// Error types that backend should use consistently
export const ERROR_TYPES = {
    // Authentication (401) - Backend defined
    AUTHENTICATION_FAILED: "authentication_failed",
    SESSION_ERROR: "session_error",
    NO_REFRESH_TOKEN: "no_refresh_token",
    REFRESH_FAILED: "refresh_failed",

    // Validation (400) - Backend defined
    INVALID_INPUT: "invalid_input",
    INVALID_QUERY: "invalid_query",
    INVALID_FIELD: "invalid_field",
    INVALID_OPERATION: "invalid_operation",
    INVALID_SYNTAX: "invalid_syntax",

    // Client errors (4xx) - Backend defined
    NOT_FOUND: "not_found",

    // Server Errors (500+) - Backend defined
    INTERNAL_ERROR: "internal_error",

    // Network/Connection Errors - Frontend only
    NETWORK_ERROR: "network_error",
    CONNECTION_ERROR: "connection_error",
} as const;

export type ErrorType = (typeof ERROR_TYPES)[keyof typeof ERROR_TYPES];

interface ErrorContext {
    component?: string;
    lifecycle?: string;
    route?: string;
    timestamp?: Date;
    userAgent?: string;
    sessionId?: string;
    userId?: string;
    buildId?: string;
    promise?: Promise<unknown>;
    errorId?: string;
    requestId?: string;
    retryCount?: number;
    [key: string]: unknown;
}

interface ErrorHandlerOptions {
    enableConsoleLogging?: boolean;
    enableToastNotifications?: boolean;
    enableErrorReporting?: boolean;
    maxRetries?: number;
    retryDelay?: number;
    retryableStatuses?: number[];
    excludeFromRetry?: string[];
}

interface ErrorToastOptions {
    title: string;
    description: string;
    color: "error" | "warning" | "info";
}

// Global state for error tracking and retry management
const errorState = reactive({
    retryCounters: new Map<string, number>(),
    rateLimitResets: new Map<string, number>(),
    isMaintenanceMode: false,
    lastNetworkError: null as Date | null,
});

/**
 * Parse API error and return user-friendly toast options
 */
function parseApiError(error: unknown): ErrorToastOptions {
    console.log("Parsing API error:", error);

    let apiError: UnifiedApiError;

    // Extract the actual API error object
    if (error instanceof Error && error.message) {
        try {
            const parsed = JSON.parse(error.message);
            if (typeof parsed === "object" && parsed !== null && ("status" in parsed || "statusCode" in parsed)) {
                apiError = parsed as UnifiedApiError;
            } else {
                apiError = error as unknown as UnifiedApiError;
            }
        } catch {
            apiError = error as unknown as UnifiedApiError;
        }
    } else {
        apiError = error as UnifiedApiError;
    }

    const status = apiError.status || (apiError as UnifiedApiError).statusCode || 500;
    const errorType = apiError.details?.error;

    // Safely extract error message
    let errorMessage: string = "An error occurred";
    if (apiError.details?.message && typeof apiError.details.message === "string") {
        errorMessage = apiError.details.message;
    } else if (apiError.message && typeof apiError.message === "string") {
        errorMessage = apiError.message;
    } else if (apiError.details?.message) {
        errorMessage = JSON.stringify(apiError.details.message);
    } else if (apiError.message) {
        errorMessage = JSON.stringify(apiError.message);
    }

    console.log("Status:", status, "Error Type:", errorType, "Message:", errorMessage);

    // Handle authentication errors (401)
    if (status === 401) {
        switch (errorType) {
            case ERROR_TYPES.SESSION_ERROR:
                return {
                    title: "Authentication Required",
                    description:
                        "You need to log in to access this feature. If you were previously logged in, try clearing cookies and logging in again to refresh your token.",
                    color: "warning",
                };
            case ERROR_TYPES.NO_REFRESH_TOKEN:
                return {
                    title: "Session Expired",
                    description: "Your session has expired and no refresh token is available. Please log in again.",
                    color: "warning",
                };
            case ERROR_TYPES.REFRESH_FAILED:
                return {
                    title: "Session Refresh Failed",
                    description: "Your session could not be refreshed. Please log in again to continue.",
                    color: "warning",
                };
            case ERROR_TYPES.AUTHENTICATION_FAILED:
            default:
                return {
                    title: "Unauthorized",
                    description:
                        "Authentication failed. Please try clearing your cookies and logging in again to refresh your token. If this does not help, contact website admins for help.",
                    color: "warning",
                };
        }
    }

    // Handle authorization errors (403)
    if (status === 403) {
        const requiredRole = apiError.details?.required_role;

        // If we have a clear error message from the backend, use it
        if (errorMessage && errorMessage !== "An error occurred") {
            return {
                title: "Permission Denied",
                description: errorMessage,
                color: "error",
            };
        }

        if (requiredRole) {
            return {
                title: "Insufficient Permissions",
                description: `You need the "${requiredRole}" role to access this feature. Please contact the site administrators to request the required permissions.`,
                color: "error",
            };
        }

        return {
            title: "Permission Denied",
            description:
                "You don't have the required permissions for this action. Please contact the site administrators to request access.",
            color: "error",
        };
    }

    // Handle validation errors (400)
    if (status === 400) {
        // Handle specific search validation errors
        switch (errorType) {
            case ERROR_TYPES.INVALID_FIELD:
                return {
                    title: "Invalid Field",
                    description:
                        errorMessage ||
                        "The field you're trying to search is not available. Please check the field name and try again.",
                    color: "error",
                };
            case ERROR_TYPES.INVALID_OPERATION:
                return {
                    title: "Invalid Operation",
                    description:
                        errorMessage ||
                        "The operation you're trying to perform is not supported for this field. Please use a different operator.",
                    color: "error",
                };
            case ERROR_TYPES.INVALID_QUERY:
                return {
                    title: "Invalid Search Query",
                    description:
                        errorMessage ||
                        "Your search query contains invalid syntax. Please check your query and try again.",
                    color: "error",
                };
            case ERROR_TYPES.INVALID_SYNTAX:
                return {
                    title: "Syntax Error",
                    description:
                        errorMessage ||
                        "There's a syntax error in your query. Please check your search syntax and try again.",
                    color: "error",
                };
        }

        if (errorType === ERROR_TYPES.INVALID_INPUT && apiError.details?.validation_errors) {
            const validationErrors = apiError.details.validation_errors;
            const fieldErrors = Object.entries(validationErrors)
                .map(([field, errors]) => {
                    const errorStr = Array.isArray(errors)
                        ? errors.join(", ")
                        : typeof errors === "string"
                        ? errors
                        : JSON.stringify(errors);
                    return `${field}: ${errorStr}`;
                })
                .join("; ");
            return {
                title: "Validation Error",
                description: `Please fix the following errors: ${fieldErrors}`,
                color: "error",
            };
        }
        return {
            title: "Invalid Request",
            description: errorMessage || "The request contains invalid data. Please check your input and try again.",
            color: "error",
        };
    }

    // Handle not found errors (404)
    if (status === 404) {
        switch (errorType) {
            case ERROR_TYPES.NOT_FOUND:
            default:
                return {
                    title: "Not Found",
                    description: "The requested resource was not found. It may have been deleted or moved.",
                    color: "error",
                };
        }
    }

    // Handle server errors (500+)
    if (status >= 500) {
        switch (errorType) {
            case ERROR_TYPES.INTERNAL_ERROR:
                return {
                    title: "Internal Server Error",
                    description:
                        "An internal server error occurred. Please try again later or contact administrators if the problem persists.",
                    color: "error",
                };
            default:
                // For generic server errors, provide more helpful messaging
                if (status === 502 || status === 503 || status === 504) {
                    return {
                        title: "Server Temporarily Unavailable",
                        description:
                            "The server is temporarily unavailable or under maintenance. Please try again in a few minutes.",
                        color: "warning",
                    };
                }
                return {
                    title: "Server Error",
                    description: `The server encountered an error (${status}). This is not an authentication issue. Please try again later or contact administrators if the problem persists.`,
                    color: "error",
                };
        }
    }

    // Handle other client errors (4xx)
    if (status >= 400 && status < 500) {
        return {
            title: "Request Error",
            description: errorMessage || "There was a problem with your request. Please try again.",
            color: "error",
        };
    }

    // Generic error fallback
    const browserShortcut = navigator.platform.toLowerCase().includes("mac") ? "⌘+⌥+I" : "F12";
    return {
        title: "Unknown Error",
        description: `An unexpected error occurred: ${errorMessage || "Unknown error"}.

For troubleshooting:
• Check browser console (${browserShortcut}) for details
• Clear cookies and try again
• Contact site administrators if the problem persists`,
        color: "error",
    };
}

// Helper functions
function isApiError(error: unknown): error is UnifiedApiError {
    // Check if it's a direct API error object
    if (
        typeof error === "object" &&
        error !== null &&
        ("status" in error || "statusCode" in error) &&
        "message" in error
    ) {
        return true;
    }

    // Check if it's an Error object with a JSON string message containing API error
    if (error instanceof Error && error.message) {
        try {
            const parsed = JSON.parse(error.message);
            return (
                typeof parsed === "object" &&
                parsed !== null &&
                ("status" in parsed || "statusCode" in parsed) &&
                "message" in parsed
            );
        } catch {
            return false;
        }
    }

    return false;
}

function isNetworkError(error: unknown): boolean {
    return (
        error instanceof TypeError ||
        (error as Error)?.name === "NetworkError" ||
        (error as { code?: string })?.code === "NETWORK_ERROR" ||
        navigator.onLine === false
    );
}

export default defineNuxtPlugin({
    name: "global-error-handler",
    setup(nuxtApp) {
        const toast = useToast();
        const { login } = useAuth();

        const options: ErrorHandlerOptions = {
            enableConsoleLogging: true,
            enableToastNotifications: true,
            enableErrorReporting: process.env.NODE_ENV === "production",
            maxRetries: 3,
            retryDelay: 1000,
            retryableStatuses: [408, 429, 500, 502, 503, 504],
            excludeFromRetry: ["/auth/", "/login", "/logout"],
        };

        // Enhanced Vue error handler with component context
        nuxtApp.vueApp.config.errorHandler = (err: unknown, instance: ComponentPublicInstance | null, info: string) => {
            // Try to preserve the original error object if it's an API error
            let error: unknown;
            if (isApiError(err)) {
                // If it's already a properly structured API error, use it directly
                error = err;
            } else if (err instanceof Error) {
                error = err;
            } else {
                // Only wrap non-API errors in Error constructor
                error = new Error(
                    typeof err === "string" ? err : err && typeof err === "object" ? JSON.stringify(err) : String(err),
                );
            }
            const context: ErrorContext = {
                component: instance?.$options.name || instance?.$options.__name || "Unknown",
                lifecycle: info,
                route: useRoute().fullPath,
                timestamp: new Date(),
                userAgent: navigator.userAgent,
            };

            console.error("[Vue Error]", { error, context });
            handleError(error, "Vue Component Error", context);
        };

        // Network status monitoring
        window.addEventListener("online", () => {
            if (errorState.lastNetworkError) {
                toast.add({
                    title: "Connection Restored",
                    description: "Your internet connection is back. Retrying failed requests...",
                    color: "success",
                    duration: 3000,
                });
                errorState.lastNetworkError = null;
            }
        });

        window.addEventListener("offline", () => {
            errorState.lastNetworkError = new Date();
            toast.add({
                title: "Connection Lost",
                description: "Check your internet connection. We'll retry when it's restored.",
                color: "warning",
                progress: false,
            });
        });

        // Global unhandled promise rejection handler
        window.addEventListener("unhandledrejection", (event) => {
            const context: ErrorContext = {
                component: "Global",
                lifecycle: "Promise Rejection",
                route: useRoute().fullPath,
                timestamp: new Date(),
                userAgent: navigator.userAgent,
                promise: event.promise,
            };

            console.error("[Unhandled Promise Rejection]", { reason: event.reason, context });
            event.preventDefault();
            handleError(event.reason, "Unhandled Promise Rejection", context);
        });

        // Core error handling function
        function handleError(error: unknown, contextName: string, context?: ErrorContext): boolean {
            if (options.enableConsoleLogging) {
                console.error(`[Error Handler - ${contextName}]`, { error, context });
            }

            // Skip API errors from useApiClient for non-component errors - they're already handled there
            if (
                isApiError(error) &&
                contextName !== "Vue Component Error" &&
                contextName !== "Unhandled Promise Rejection"
            ) {
                return false; // Let useApiClient handle it
            }

            // Check for network errors
            if (isNetworkError(error)) {
                return handleNetworkError();
            }

            // Check if it's an API error from Vue components or unhandled promises
            if (isApiError(error)) {
                return handleApiError(error, contextName, context);
            }

            // Handle generic JavaScript errors
            return handleGenericError(error);
        }

        function handleApiError(error: UnifiedApiError, contextName: string, context?: ErrorContext): boolean {
            const requestKey = context?.route || "unknown";

            // Handle authentication errors (401)
            if (error.status === 401) {
                return handleAuthError(error);
            }

            // Handle authorization errors (403)
            if (error.status === 403) {
                return handleAuthorizationError(error);
            }

            // Handle retryable server errors
            if (options.retryableStatuses?.includes(error.status)) {
                const shouldRetry = checkRetryEligibility(requestKey, context);
                if (shouldRetry) {
                    return scheduleRetry(error, requestKey);
                }
            }

            // Show user-friendly error message
            if (options.enableToastNotifications) {
                const toastOptions = parseApiError(error);
                toast.add({
                    ...toastOptions,
                    duration: 10000,
                });
            }

            return true;
        }

        function handleAuthError(error: UnifiedApiError): boolean {
            // Clear any existing retry counters for auth errors
            errorState.retryCounters.clear();

            if (options.enableToastNotifications) {
                const toastOptions = parseApiError(error);
                toast.add({
                    ...toastOptions,
                    actions: [
                        {
                            label: "Login",
                            onClick: () => login(),
                        },
                    ],
                });
            }

            return true;
        }

        function handleAuthorizationError(error: UnifiedApiError): boolean {
            if (options.enableToastNotifications) {
                const toastOptions = parseApiError(error);
                toast.add({
                    ...toastOptions,
                });
            }

            return true;
        }

        function handleNetworkError(): boolean {
            errorState.lastNetworkError = new Date();

            if (options.enableToastNotifications) {
                toast.add({
                    title: "Connection Problem",
                    description:
                        "Unable to connect to the server. This is not an authentication issue. Please check your internet connection and try again.",
                    color: "status-failed",
                    duration: 10000, // Show longer for network issues
                });
            }

            return true;
        }

        function handleGenericError(error: unknown): boolean {
            let errorMessage: string;

            if (error instanceof Error) {
                errorMessage = error.message;
            } else if (typeof error === "string") {
                errorMessage = error;
            } else if (error && typeof error === "object") {
                // Try to extract meaningful information from error objects
                const errorObj = error as Record<string, unknown>;
                if (errorObj.message && typeof errorObj.message === "string") {
                    errorMessage = errorObj.message;
                } else if (errorObj.details && typeof errorObj.details === "object") {
                    const details = errorObj.details as Record<string, unknown>;
                    if (details.message && typeof details.message === "string") {
                        errorMessage = details.message;
                    } else {
                        errorMessage = JSON.stringify(errorObj, null, 2);
                    }
                } else {
                    errorMessage = JSON.stringify(errorObj, null, 2);
                }
            } else {
                errorMessage = String(error);
            }

            if (options.enableToastNotifications) {
                toast.add({
                    title: "Application Error",
                    description: `An unexpected error occurred: ${errorMessage}`,
                    color: "error",
                });
            }

            return true;
        }

        function checkRetryEligibility(requestKey: string, context?: ErrorContext): boolean {
            const currentRetries = errorState.retryCounters.get(requestKey) || 0;
            const maxRetries = options.maxRetries || 3;

            // Check if route is excluded from retry
            if (options.excludeFromRetry?.some((pattern) => context?.route?.includes(pattern))) {
                return false;
            }

            // Check if we're still within rate limit
            const rateLimitReset = errorState.rateLimitResets.get(requestKey);
            if (rateLimitReset && Date.now() < rateLimitReset) {
                return false;
            }

            return currentRetries < maxRetries;
        }

        function scheduleRetry(error: UnifiedApiError, requestKey: string): boolean {
            const currentRetries = errorState.retryCounters.get(requestKey) || 0;
            const newRetryCount = currentRetries + 1;

            errorState.retryCounters.set(requestKey, newRetryCount);

            const delay = (options.retryDelay || 1000) * Math.pow(2, currentRetries); // Exponential backoff

            if (options.enableToastNotifications) {
                toast.add({
                    title: "Retrying Request",
                    description: `Attempt ${newRetryCount} of ${options.maxRetries}. Retrying in ${
                        delay / 1000
                    } seconds...`,
                    color: "info",
                });
            }

            // Note: Actual retry logic would need to be implemented by the calling code
            // This just tracks the retry state and shows user feedback

            return true;
        }

        // Expose API for programmatic error handling
        return {
            provide: {
                errorHandler: {
                    handle: handleError,
                    parseApiError,
                    isApiError,
                    isNetworkError,
                    ERROR_TYPES,
                },
            },
        };
    },
});
