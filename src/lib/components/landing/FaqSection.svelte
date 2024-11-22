<script lang="ts">
    import { getContext, onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import type { i18n as i18nType } from 'i18next';
    import gsap from 'gsap';
    import ScrollTrigger from 'gsap/ScrollTrigger';

    let i18n = getContext<i18nType>('i18n');
    let openIndex = -1;
    let sectionRef: HTMLElement;
    let headingRef: HTMLElement;

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }

    function toggleAccordion(index: number) {
        openIndex = openIndex === index ? -1 : index;
    }

    onMount(() => {
        gsap.registerPlugin(ScrollTrigger);

        gsap.to(sectionRef, {
            yPercent: -100,
            opacity: 0,
            scrollTrigger: {
                trigger: sectionRef,
                scroller: "body",
                scrub: 1,
                start: "top 20%",
                end: "top -20%",
            },
        });

        gsap.from(headingRef, {
            scale: 0,
            opacity: 0,
            scrollTrigger: {
                trigger: ".faqSection",
                scroller: "body",
                scrub: true,
                end: "top 100%",
            },
        });
    });
</script>

<section bind:this={sectionRef} class="py-16 bg-gray-50 dark:bg-gray-900">
    <div class="container mx-auto px-4 max-w-[1440px]">
        <div bind:this={headingRef}>
            <h2 class="text-4xl md:text-5xl font-['Inter'] font-semibold text-center mb-16 text-gray-900 dark:text-gray-50">
                {t('cicero.faq.title')}
            </h2>
        </div>

        <div class="mt-[50px]">
            <div class="grid md:grid-cols-2 gap-8">
                <div class="flex flex-col gap-5">
                    {#each [0, 1] as index}
                        <button
                            class="w-full text-left p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm hover:shadow-md transition-all duration-200"
                            on:click={() => toggleAccordion(index)}
                            aria-expanded={openIndex === index}
                        >
                            <div class="flex justify-between items-center">
                                <h3 class="text-xl font-semibold text-gray-900 dark:text-gray-50">
                                    {t(`cicero.faq.questions.${index}.question`)}
                                </h3>
                                <svg
                                    class="w-6 h-6 transform transition-transform duration-200 text-gray-900 dark:text-gray-50 {openIndex === index ? 'rotate-180' : ''}"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        stroke-width="2"
                                        d="M19 9l-7 7-7-7"
                                    />
                                </svg>
                            </div>
                            {#if openIndex === index}
                                <p class="mt-4 text-gray-700 dark:text-gray-300">
                                    {t(`cicero.faq.questions.${index}.answer`)}
                                </p>
                            {/if}
                        </button>
                    {/each}
                </div>
                <div class="flex flex-col gap-5">
                    {#each [2, 3] as index}
                        <button
                            class="w-full text-left p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm hover:shadow-md transition-all duration-200"
                            on:click={() => toggleAccordion(index)}
                            aria-expanded={openIndex === index}
                        >
                            <div class="flex justify-between items-center">
                                <h3 class="text-xl font-semibold text-gray-900 dark:text-gray-50">
                                    {t(`cicero.faq.questions.${index}.question`)}
                                </h3>
                                <svg
                                    class="w-6 h-6 transform transition-transform duration-200 text-gray-900 dark:text-gray-50 {openIndex === index ? 'rotate-180' : ''}"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        stroke-width="2"
                                        d="M19 9l-7 7-7-7"
                                    />
                                </svg>
                            </div>
                            {#if openIndex === index}
                                <p class="mt-4 text-gray-700 dark:text-gray-300">
                                    {t(`cicero.faq.questions.${index}.answer`)}
                                </p>
                            {/if}
                        </button>
                    {/each}
                </div>
            </div>
        </div>

        <div class="flex justify-center mt-16">
            <button 
                class="bg-gray-900 dark:bg-gray-50 text-gray-50 dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 px-6 py-3 font-sans text-lg font-medium leading-[20px] rounded-full uppercase transition-all duration-300 hover:scale-105"
                on:click={() => goto('/auth')}
            >
                {t('cicero.hero.cta')}
            </button>
        </div>
    </div>
</section>
