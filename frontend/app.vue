<template>
    <UApp class="min-h-screen flex flex-col">
        <!-- Skip to main content link for accessibility -->
        <a href="#main-content" class="skip-link">Skip to main content</a>

        <!-- Navigation Header -->
        <header class="bg-space-50 border-space-200">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <!-- Mobile Layout (responsive stacked) -->
                <div class="flex flex-col py-2 sm:hidden">
                    <!-- First row: Logo, Title, Contact (icon), and Auth -->
                    <div class="flex items-center justify-between">
                        <div class="flex items-center space-x-3 flex-1 min-w-0">
                            <NuxtLink to="/" class="flex items-center flex-shrink-0" @click="handleLogoClick">
                                <NuxtImg src="/logo.png" :alt="appTitle" class="h-8 w-auto" />
                            </NuxtLink>
                            <h1 class="text-lg font-semibold font-sans truncate select-none">
                                {{ appTitle }}
                            </h1>
                        </div>
                        <div class="flex items-center gap-2 flex-shrink-0">
                            <!-- Admin Modal - Icon only on mobile, only for authenticated users -->
                            <AdminModal v-if="isAuthenticated" icon-only />
                            <!-- Contact Modal - Icon only on mobile -->
                            <ContactModal icon-only />
                            <!-- Auth Section - will show icon for login or sign out button -->
                            <AuthSection mobile-compact logout-only />
                        </div>
                    </div>

                    <!-- Second row: User info (only when logged in) -->
                    <div v-if="isAuthenticated" class="flex items-center justify-end mt-2 w-full">
                        <AuthSection user-info-only />
                    </div>
                </div>

                <!-- Desktop Layout (single row) -->
                <div class="hidden sm:flex items-center h-16">
                    <!-- Left: Logo -->
                    <div class="flex items-center">
                        <NuxtLink class="flex items-center cursor-pointer" @click="handleLogoClick">
                            <NuxtImg src="/logo.png" :alt="appTitle" class="h-8 w-auto" />
                        </NuxtLink>
                    </div>

                    <!-- Center: App Title -->
                    <h1 class="px-5 text-xl font-semibold font-sans whitespace-nowrap select-none">
                        {{ appTitle }}
                    </h1>

                    <!-- Right: Contact, Admin and Authentication Section -->
                    <div class="ml-auto flex items-center space-x-4">
                        <AdminModal v-if="isAuthenticated" />
                        <ContactModal />
                        <AuthSection />
                    </div>
                </div>
            </div>
        </header>

        <!-- Main Content -->
        <main id="main-content" class="flex-1">
            <NuxtPage />
        </main>

        <!-- Footer -->
        <AppFooter />
    </UApp>
</template>

<script setup lang="ts">
import AuthSection from "~/components/auth/AuthSection.vue";
import AppFooter from "~/components/AppFooter.vue";
import ContactModal from "~/components/ContactModal.vue";
import AdminModal from "~/components/AdminModal.vue";

// Check authentication status on app initialization
const { checkAuthStatus, user } = useAuth();
const { initializeNavigation } = useDynamicNavigation();
const { appTitle } = useAppConfiguration();
const router = useRouter();

// Check if user is authenticated
const isAuthenticated = computed(() => APP_CONFIG.auth.enabled && !!user.value?.given_name);

const handleLogoClick = async (event: Event) => {
    // Prevent the default link navigation
    event.preventDefault();

    // Try to use global search controller first
    const { clearSearchAndRefresh, hasController } = useGlobalSearchControl();

    if (hasController.value) {
        // Use the global search controller to clear search and refresh
        await clearSearchAndRefresh();
        // Navigate to home page
        await router.push({ path: "/" });
    } else {
        // Fallback to route-based navigation if no controller is available
        await router.push({ path: "/", query: { q: "" } });
    }
};

onMounted(async () => {
    // Initialize navigation configuration globally
    await initializeNavigation();

    // Check authentication status
    await checkAuthStatus();
});
</script>

<!--
Powered by friendship!
                                                    /
                                                  .7
                                       \       , //
                                       |\.--._/|//
                                      /\ ) ) ).'/
                                     /(  \  // /
                                    /(   J`((_/ \
                                   / ) | _\     /
                                  /|)  \  eJ    L
                                 |  \ L \   L   L
                                /  \  J  `. J   L
                                |  )   L   \/   \
                               /  \    J   (\   /
             _....___         |  \      \   \```
      ,.._.-'        '''--...-||\     -. \   \
    .'.=.'                    `         `.\ [ Y
   /   /                                  \]  J
  Y / Y                                    Y   L
  | | |          \                         |   L
  | | |           Y                        A  J
  |   I           |                       /I\ /
  |    \          I             \        ( |]/|
  J     \         /._           /        -tI/ |
   L     )       /   /'-------'J           `'-:.
   J   .'      ,'  ,' ,     \   `'-.__          \
    \ T      ,'  ,'   )\    /|        ';'---7   /
     \|    ,'L  Y...-' / _.' /         \   /   /
      J   Y  |  J    .'-'   /         ,--.(   /
       L  |  J   L -'     .'         /  |    /\
       |  J.  L  J     .-;.-/       |    \ .' /
       J   L`-J   L____,.-'`        |  _.-'   |
        L  J   L  J                  ``  J    |
        J   L  |   L                     J    |
         L  J  L    \                    L    \
         |   L  ) _.'\                    ) _.'\
         L    \('`    \                  ('`    \
          ) _.'\`-....'                   `-....'
         ('`    \
          `-.___/   sk
 -->
