<script lang="ts">
    import { getContext } from 'svelte';
    import type { i18n as i18nType } from 'i18next';

    let i18n = getContext<i18nType>('i18n');
    let year = new Date().getFullYear();

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }
</script>

<footer class="bg-gray-50 dark:bg-gray-900 py-12">
    <div class="container mx-auto px-4 max-w-[1440px]">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div class="col-span-1 md:col-span-2">
                <img
                    src="/static/favicon.png"
                    class="w-10 rounded-full mb-4"
                    alt="logo"
                />
                <p class="text-gray-600 dark:text-gray-400 max-w-sm">
                    {t('cicero.information.description')}
                </p>
            </div>
            <div class="col-span-1">
                <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">Links</h3>
                <ul class="space-y-2">
                    <li>
                        <a href="#" class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
                            {t('cicero.footer.aboutUs')}
                        </a>
                    </li>
                    <li>
                        <a href="#" class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
                            {t('cicero.footer.blog')}
                        </a>
                    </li>
                    <li>
                        <a href="#" class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
                            {t('cicero.footer.contactUs')}
                        </a>
                    </li>
                </ul>
            </div>
            <div class="col-span-1">
                <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">Legal</h3>
                <ul class="space-y-2">
                    <li>
                        <a href="#" class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
                            {t('cicero.footer.termsPrivacy')}
                        </a>
                    </li>
                    <li>
                        <a href="#" class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
                            {t('cicero.footer.cookieSettings')}
                        </a>
                    </li>
                </ul>
            </div>
        </div>
        <div class="border-t border-gray-200 dark:border-gray-800 mt-12 pt-8 text-center">
            <p class="text-gray-600 dark:text-gray-400">
                © {year} Cicero. {t('cicero.footer.rights')}
            </p>
        </div>
    </div>
</footer>
