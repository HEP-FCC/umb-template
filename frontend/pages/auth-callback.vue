<template>
    <div class="min-h-screen flex items-center justify-center bg-space-50 px-4">
        <div class="max-w-md w-full">
            <!-- Loading state -->
            <UCard v-if="isLoading" class="text-center">
                <template #header>
                    <div class="flex items-center justify-center gap-3">
                        <UIcon name="i-heroicons-arrow-path" class="w-6 h-6 animate-spin text-eco-500" />
                        <h2 class="text-xl font-semibold">Authenticating</h2>
                    </div>
                </template>

                <p>Please wait while we complete your login with CERN SSO...</p>

                <div class="mt-4">
                    <div class="w-full bg-space-200ounded-full h-2">
                        <div class="bg-eco-500 h-2 rounded-full animate-pulse" style="width: 60%" />
                    </div>
                </div>
            </UCard>

            <!-- Error state -->
            <UCard v-else-if="error" class="text-center">
                <template #header>
                    <div class="flex items-center justify-center gap-3">
                        <UIcon name="i-heroicons-exclamation-triangle" class="w-6 h-6 text-earth" />
                        <h2 class="text-xl font-semibold">Authentication Failed Please try logging in again.</h2>
                    </div>
                </template>

                <p class="mb-6">
                    {{ error }}
                </p>

                <UButton color="primary" variant="solid" icon="i-heroicons-home" block @click="redirectToHome">
                    Return to Home
                </UButton>
            </UCard>

            <!-- Success state -->
            <UCard v-else class="text-center">
                <template #header>
                    <div class="flex items-center justify-center gap-3">
                        <UIcon name="i-heroicons-check-circle" class="w-6 h-6 text-eco-500" />
                        <h2 class="text-xl font-semibold">Authentication Successful!</h2>
                    </div>
                </template>

                <p>You have been successfully logged in with CERN SSO.</p>

                <p>Redirecting you to the main application...</p>

                <div class="mt-4">
                    <div class="w-full bg-space-200 rounded-full h-2">
                        <div class="bg-eco-500 h-2 rounded-full transition-all duration-1000" style="width: 100%" />
                    </div>
                </div>
            </UCard>
        </div>
    </div>
</template>

<script setup lang="ts">
// This page is now primarily used for handling redirects after backend auth
// The OAuth flow is handled entirely by the backend

const route = useRoute();
const router = useRouter();
const { checkAuthStatus } = useAuth();

const isLoading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
    try {
        // Check for error in query params (e.g., access denied)
        const errorParam = route.query.error as string;
        if (errorParam) {
            if (errorParam === "access_denied") {
                error.value = "Access denied. You don't have the required permissions.";
            } else {
                error.value = "Authentication failed. Please try again.";
            }
            isLoading.value = false;
            return;
        }

        // The backend has already handled the OAuth callback and set the session cookie
        // Just check auth status to update the frontend state
        await checkAuthStatus();

        // Show success message briefly before redirect
        isLoading.value = false;

        // Redirect to home after successful authentication
        setTimeout(() => {
            router.push("/");
        }, 2000);
    } catch (err) {
        console.error("Auth callback error:", err);
        error.value = "An error occurred during authentication.";
        isLoading.value = false;
    }
});

function redirectToHome() {
    router.push("/");
}
</script>
