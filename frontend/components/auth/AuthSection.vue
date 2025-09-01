<template>
    <div class="flex items-center gap-4 p-2">
        <!-- Authentication controls - only show if auth is enabled -->
        <div v-if="showAuthControls && !isAuthenticated" class="flex items-center">
            <UButton
                :loading="isLoading"
                color="primary"
                variant="solid"
                :size="mobileCompact ? 'md' : 'lg'"
                icon="i-heroicons-user-circle"
                class="cursor-pointer"
                :label="mobileCompact ? undefined : isLoading ? 'Signing in...' : 'Sign in'"
                @click="handleLogin"
            />
        </div>

        <div v-else-if="showAuthControls && isAuthenticated" class="flex items-center gap-4">
            <!-- User info only mode - just display user info -->
            <div v-if="userInfoOnly" class="flex items-center gap-3">
                <div class="text-right">
                    <div class="text-sm font-medium">
                        {{ displayName }}
                    </div>
                    <div class="text-xs">
                        {{ displayRoles }}
                    </div>
                </div>
            </div>
            <!-- Logout only mode - just logout button -->
            <div v-else-if="logoutOnly" class="flex items-center">
                <UButton
                    :loading="isLoading"
                    color="energy"
                    variant="outline"
                    :size="mobileCompact ? 'md' : 'lg'"
                    icon="i-heroicons-arrow-right-on-rectangle"
                    :label="mobileCompact ? undefined : 'Sign out'"
                    class="cursor-pointer"
                    @click="handleLogout"
                />
            </div>
            <!-- Regular mode with logout button and user info -->
            <div v-else class="flex items-center gap-3">
                <div class="text-right">
                    <div class="text-sm font-medium">
                        {{ displayName }}
                    </div>
                    <div class="text-xs">
                        {{ displayRoles }}
                    </div>
                </div>
                <UButton
                    :loading="isLoading"
                    color="energy"
                    variant="outline"
                    :size="mobileCompact ? 'md' : 'lg'"
                    icon="i-heroicons-arrow-right-on-rectangle"
                    :label="mobileCompact ? undefined : 'Sign out'"
                    class="cursor-pointer"
                    @click="handleLogout"
                />
            </div>
        </div>

        <!-- Error alert -->
        <UAlert
            v-if="error"
            icon="i-heroicons-exclamation-triangle"
            color="error"
            variant="soft"
            :title="error"
            :close-button="{
                icon: 'i-heroicons-x-mark-20-solid',
                color: 'neutral',
                variant: 'ghost',
                size: 'xs',
                class: 'w-6 h-6 p-1 hover:bg-gray-100 rounded cursor-pointer flex items-center justify-center shrink-0',
            }"
            class="fixed top-20 right-4 z-50 max-w-sm"
            @close="clearError"
        />
    </div>
</template>

<script setup lang="ts">
interface Props {
    mobileCompact?: boolean;
    userInfoOnly?: boolean;
    logoutOnly?: boolean;
}

withDefaults(defineProps<Props>(), {
    mobileCompact: false,
    userInfoOnly: false,
    logoutOnly: false,
});

const { authState, login, logout, clearError, isAuthDisabled } = useAuth();

// Computed properties for easy access
const isAuthenticated = computed(() => authState.value.isAuthenticated);
const user = computed(() => authState.value.user);
const isLoading = computed(() => authState.value.isLoading);
const error = computed(() => authState.value.error);

// Show authentication controls only if auth is enabled
const showAuthControls = computed(() => !isAuthDisabled.value);

// Computed display name - just the full name
const displayName = computed(() => {
    if (user.value?.given_name && user.value?.family_name) {
        return `${user.value.given_name} ${user.value.family_name}`;
    }
    return user.value?.preferred_username || "User";
});

// Computed display roles - filtered roles or "no roles"
const displayRoles = computed(() => {
    // Filter CERN roles to exclude the default "authorized" role
    let roles: string[] = [];
    if (user.value?.cern_roles && Array.isArray(user.value.cern_roles)) {
        roles = user.value.cern_roles.filter((role) => role !== "default-role");
    } else if (user.value?.groups && Array.isArray(user.value.groups)) {
        // Fallback to groups if cern_roles not available, also filter "authorized"
        roles = user.value.groups.filter((role) => role !== "default-role");
    }

    // Return roles or "no roles" if empty
    return roles.length > 0 ? roles.join(", ") : "no roles";
});

// Handle login
function handleLogin() {
    login();
}

// Handle logout
async function handleLogout() {
    await logout();
}
</script>
