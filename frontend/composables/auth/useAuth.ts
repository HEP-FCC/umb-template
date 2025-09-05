import { onMounted, getCurrentInstance } from "vue";

interface User {
    given_name?: string;
    family_name?: string;
    preferred_username?: string;
    cern_roles?: string[];
    groups?: string[];
    [key: string]: unknown;
}

interface AuthState {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    error: string | null;
}

/**
 * Authentication composable for CERN OAuth with cookie-based sessions
 * Handles login, logout, and user session management
 */
export function useAuth() {
    const { initiateLogin, logoutUser, getSessionStatus, manualRefreshToken } = useApiClient();

    // Use global state to ensure consistency across components
    const authState = useState<AuthState>(
        "auth-state",
        (): AuthState => ({
            user: null,
            isAuthenticated: false,
            isLoading: false,
            error: null,
        }),
    );

    // Check if auth is disabled based on user object
    const isAuthDisabled = computed(() => {
        return (
            authState.value.user && typeof authState.value.user === "object" && "auth_disabled" in authState.value.user
        );
    });

    // Check auth status on app startup (only in client-side components)
    const checkAuthOnMount = () => {
        if (getCurrentInstance()) {
            onMounted(async () => {
                await checkAuthStatus();
            });
        }
    };

    /**
     * Check if user is currently authenticated by calling the backend session endpoint
     */
    async function checkAuthStatus(): Promise<void> {
        authState.value.isLoading = true;
        authState.value.error = null;

        try {
            // If auth is disabled in frontend config, behave as if always authenticated
            if (!APP_CONFIG.auth.enabled) {
                authState.value.isAuthenticated = true;  // Changed from false to true
                authState.value.user = {
                    preferred_username: "Guest User",
                    email: "guest@example.com",
                    name: "Guest User",
                    auth_disabled: true,
                } as User;
                authState.value.isLoading = false;
                return;
            }

            const sessionData = await getSessionStatus();

            if (sessionData.authenticated && sessionData.user) {
                authState.value.isAuthenticated = true;
                authState.value.user = sessionData.user as User;
                authState.value.error = null;
            } else {
                authState.value.isAuthenticated = false;
                authState.value.user = null;
            }
        } catch (error) {
            console.error("Authentication check failed:", error);

            // Distinguish between different types of errors
            const apiError = error as Record<string, unknown>;
            const status = (apiError?.status as number) || (apiError?.statusCode as number) || 500;
            const errorType = (apiError?.details as Record<string, unknown>)?.error_type;

            // Only set authentication error for actual auth failures, not server/network issues
            if (status === 401 || status === 403 || errorType === "authentication_error") {
                authState.value.error = "Authentication check failed. Please try signing in again.";
            } else if (status >= 500 || errorType === "server_error") {
                authState.value.error = "Server is currently unreachable. Please try again later.";
            } else if (errorType === "network_error") {
                authState.value.error = "Network connection problem. Please check your internet connection.";
            } else {
                authState.value.error = "Unable to verify authentication status. Please try refreshing the page.";
            }

            authState.value.isAuthenticated = false;
            authState.value.user = null;
        } finally {
            authState.value.isLoading = false;
        }
    }

    /**
     * Initiate login flow - redirects to CERN OAuth
     */
    function login(): void {
        // Don't attempt login if auth is disabled
        if (isAuthDisabled.value) {
            console.log("Authentication is disabled, login not available");
            return;
        }

        authState.value.error = null;
        initiateLogin();
    }

    /**
     * Logout user and clear cookie
     */
    async function logout(): Promise<void> {
        // Don't attempt logout if auth is disabled
        if (isAuthDisabled.value) {
            console.log("Authentication is disabled, logout not available");
            return;
        }

        authState.value.isLoading = true;
        authState.value.error = null;

        try {
            // Get logout URL from backend and clear cookies
            const logoutResponse = await logoutUser();

            // Verify that we are now logged out by checking session status
            try {
                const sessionData = await getSessionStatus();
                if (sessionData.authenticated) {
                    console.warn("Session still appears authenticated after logout attempt");
                    authState.value.error = "Logout may not have completed successfully";
                }
            } catch (error) {
                // Expected - session should return 401 or show as not authenticated
                console.log("Session status check after logout:", error);
            }

            // Update auth state to reflect logout
            authState.value.isAuthenticated = false;
            authState.value.user = null;

            // Redirect to CERN SSO logout if URL provided
            if (logoutResponse?.logout_url) {
                window.location.href = logoutResponse.logout_url;
            }
        } catch (error) {
            console.error("Logout failed:", error);
            // Still clear auth state even if logout call fails
            authState.value.isAuthenticated = false;
            authState.value.user = null;
        } finally {
            authState.value.isLoading = false;
        }
    }

    /**
     * Handle OAuth callback - not needed with cookie auth,
     * but kept for compatibility
     */
    async function handleAuthCallback(): Promise<void> {
        // With cookie-based auth, this is handled by the backend
        // Just check auth status after callback
        await checkAuthStatus();
    }

    /**
     * Clear authentication error
     */
    function clearError(): void {
        authState.value.error = null;
    }

    /**
     * Get access token for API calls from backend session
     */
    async function getAccessToken(): Promise<string | null> {
        try {
            const sessionData = await getSessionStatus();

            if (sessionData.authenticated) {
                // The token is handled server-side with HttpOnly cookies
                // For API calls, we rely on the cookie being sent automatically
                return "session-based"; // Placeholder since we use cookie auth
            }

            throw new Error("No access token available. Please login.");
        } catch {
            throw new Error("No access token available. Please login.");
        }
    }

    /**
     * Refresh current session for browser-based authentication
     */
    async function refreshSession(): Promise<void> {
        // Just validate the current cookie
        await checkAuthStatus();
    }

    /**
     * Proactively refresh access token
     * Useful for long-running sessions or before critical operations
     */
    async function refreshToken(): Promise<boolean> {
        authState.value.isLoading = true;
        authState.value.error = null;

        try {
            const refreshSuccess = await manualRefreshToken();

            if (refreshSuccess) {
                // Token refreshed successfully, update auth state
                await checkAuthStatus();
                return true;
            } else {
                authState.value.error = "Token refresh failed. Please sign in again.";
                authState.value.isAuthenticated = false;
                authState.value.user = null;
                return false;
            }
        } catch (error) {
            console.error("Token refresh failed:", error);
            authState.value.error = "Token refresh failed. Please sign in again.";
            authState.value.isAuthenticated = false;
            authState.value.user = null;
            return false;
        } finally {
            authState.value.isLoading = false;
        }
    }

    return {
        // Readonly state
        authState: readonly(authState),
        isAuthenticated: readonly(computed(() => authState.value.isAuthenticated)),
        user: readonly(computed(() => authState.value.user)),
        isLoading: readonly(computed(() => authState.value.isLoading)),
        error: readonly(computed(() => authState.value.error)),
        isAuthDisabled: readonly(isAuthDisabled),

        // Methods
        checkAuthStatus,
        checkAuthOnMount,
        login,
        logout,
        handleAuthCallback,
        getAccessToken,
        refreshSession,
        refreshToken,
        clearError,
    };
}
