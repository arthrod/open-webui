<script lang="ts">
    import { getContext, onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { WEBUI_NAME } from '$lib/stores';
    import type { i18n as i18nType } from 'i18next';

    let i18n = getContext<i18nType>('i18n');
    let isScrolled = false;

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }

    onMount(() => {
        const handleScroll = () => {
            if (window.scrollY > 50) {
                isScrolled = true;
            } else {
                isScrolled = false;
            }
        };

        window.addEventListener("scroll", handleScroll);

        return () => {
            window.removeEventListener("scroll", handleScroll);
        };
    });
</script>

<div class="fixed w-full z-50">
    <div class="container mx-auto px-4 max-w-[1440px]">
        <nav
            class="flex items-center transition-all duration-500 justify-between py-2 {isScrolled ? 'md:py-2' : 'md:py-4'}"
        >
            <a
                href="/"
                class="logo font-Inter hover:scale-110 transition-all px-6 py-2 rounded-md flex items-center justify-center mt-6 bg-gray-900 dark:bg-gray-50"
            >
                <h1 class="text-gray-50 dark:text-gray-900 text-[2.7rem] font-bold tracking-tight">{$WEBUI_NAME}</h1>
            </a>

            <div class="flex items-center gap-[30px]">
                <div class="social flex items-center gap-5">
                    <a 
                        href="https://github.com/open-webui/open-webui" 
                        target="_blank"
                        class="hover:scale-110 transition-all p-2 rounded-full flex items-center justify-center bg-gray-900 dark:bg-gray-50"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-gray-50 dark:text-gray-900">
                            <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
                        </svg>
                    </a>
                    <button
                        on:click={() => {
                            const html = document.documentElement;
                            html.classList.toggle('dark');
                        }}
                        class="hover:scale-110 transition-all p-2 rounded-full flex items-center justify-center bg-gray-900 dark:bg-gray-50"
                        aria-label="Toggle theme"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-gray-50 dark:text-gray-900">
                            <circle cx="12" cy="12" r="5"/>
                            <line x1="12" y1="1" x2="12" y2="3"/>
                            <line x1="12" y1="21" x2="12" y2="23"/>
                            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                            <line x1="1" y1="12" x2="3" y2="12"/>
                            <line x1="21" y1="12" x2="23" y2="12"/>
                            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                        </svg>
                    </button>
                    <button
                        on:click={() => goto('/auth')}
                        class="hover:scale-110 transition-all px-6 py-2 rounded-full flex items-center justify-center bg-gray-900 dark:bg-gray-50 text-gray-50 dark:text-gray-900 font-medium"
                    >
                        {t('Sign in')}
                    </button>
                </div>
            </div>
        </nav>
    </div>
</div>
