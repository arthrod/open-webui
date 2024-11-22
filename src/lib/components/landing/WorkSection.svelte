<script lang="ts">
    import { getContext } from 'svelte';
    import { goto } from '$app/navigation';
    import type { i18n as i18nType } from 'i18next';

    let i18n = getContext<i18nType>('i18n');

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }
</script>

<section class="py-16 md:py-24 bg-gray-50 dark:bg-gray-900">
    <div class="container mx-auto px-4 max-w-[1440px]">
        <h2 class="text-4xl md:text-5xl font-['Inter'] font-semibold text-center mb-16 text-gray-900 dark:text-gray-50">
            {t('cicero.work.title')}
        </h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12 mb-16">
            {#each [0, 1, 2, 3] as index}
                <div 
                    class="p-8 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-300 shadow-sm hover:shadow-md"
                >
                    <h3 class="text-2xl font-['Inter'] font-semibold mb-4 text-gray-900 dark:text-gray-50">
                        {t(`cicero.work.features.${index}.title`)}
                    </h3>
                    <p class="text-lg font-['Inter'] text-gray-700 dark:text-gray-300">
                        {t(`cicero.work.features.${index}.description`)}
                    </p>
                </div>
            {/each}
        </div>
        <div class="flex justify-center">
            <button 
                class="bg-gray-900 dark:bg-gray-50 text-gray-50 dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 px-6 py-3 font-sans text-lg font-medium leading-[20px] rounded-full uppercase transition-all duration-300 hover:scale-105"
                on:click={() => goto('/auth')}
            >
                {t('cicero.hero.cta')}
            </button>
        </div>
    </div>
</section>
