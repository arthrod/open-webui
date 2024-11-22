<script lang="ts">
    import { getContext } from 'svelte';
    import type { i18n as i18nType } from 'i18next';

    let i18n = getContext<i18nType>('i18n');
    let email = '';

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }

    function handleSubmit() {
        // For now, just clear the input
        // In the future, this could be connected to a newsletter service
        email = '';
    }
</script>

<section class="py-16 bg-gray-50 dark:bg-gray-900">
    <div class="container mx-auto px-4 max-w-[1440px]">
        <div class="p-4 md:p-6 lg:p-[30px] rounded-[30px] max-w-2xl mx-auto bg-gray-900 dark:bg-gray-50">
            <h2 class="text-2xl md:text-3xl font-Inter font-semibold text-center mb-6 text-gray-50 dark:text-gray-900">
                {t('cicero.newsletter.title')}
            </h2>
            <p class="text-center font-Inter text-base mb-8 max-w-md mx-auto text-gray-200 dark:text-gray-700">
                {t('cicero.newsletter.description')}
            </p>
            <form 
                class="w-full max-w-[400px] mx-auto bg-gray-800 dark:bg-white rounded-lg md:rounded-full flex max-md:flex-col py-2 pr-2 max-md:pl-2"
                on:submit|preventDefault={handleSubmit}
            >
                <input
                    type="email"
                    bind:value={email}
                    placeholder="Enter your email"
                    class="px-4 md:px-5 max-md:py-2 max-md:mb-2 font-Inter text-sm font-medium placeholder:text-gray-500 dark:placeholder:text-gray-400 rounded-full text-gray-50 dark:text-gray-900 w-full border-none outline-none bg-transparent"
                    required
                />
                <button
                    type="submit"
                    class="bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-50 hover:bg-gray-200 dark:hover:bg-gray-800 transition-all rounded-lg md:rounded-full px-6 py-2 font-Inter text-sm font-medium uppercase hover:scale-105"
                >
                    {t('cicero.newsletter.button')}
                </button>
            </form>
        </div>
    </div>
</section>
