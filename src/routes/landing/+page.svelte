<script lang="ts">
    import { goto } from '$app/navigation';
    import { WEBUI_NAME } from '$lib/stores';
    import { getContext, onMount } from 'svelte';
    import type { i18n as i18nType } from 'i18next';
    import Hero from '$lib/components/landing/Hero.svelte';
    import WorkSection from '$lib/components/landing/WorkSection.svelte';
    import FaqSection from '$lib/components/landing/FaqSection.svelte';
    import NewsletterSection from '$lib/components/landing/NewsletterSection.svelte';
    import Footer from '$lib/components/landing/Footer.svelte';
    import Navbar from '$lib/components/landing/Navbar.svelte';

    let i18n: i18nType | null = null;

    onMount(() => {
        try {
            i18n = getContext<i18nType>('i18n');
        } catch (error) {
            console.error('Failed to get i18n context:', error);
        }
    });

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }
</script>

<div class="min-h-screen bg-white dark:bg-gray-950 flex flex-col">
    <Navbar />

    <main class="flex-grow">
        <Hero />
        <WorkSection />
        <FaqSection />
        <NewsletterSection />
    </main>

    <Footer />
</div>
