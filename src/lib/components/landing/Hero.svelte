<script lang="ts">
    import { onMount, getContext } from 'svelte';
    import { goto } from '$app/navigation';
    import gsap from 'gsap';
    import ScrollTrigger from 'gsap/ScrollTrigger';
    import type { i18n as i18nType } from 'i18next';

    let i18n = getContext<i18nType>('i18n');
    let animatedText: HTMLElement;
    let heroButton: HTMLElement;
    let heroText: HTMLElement;
    let timeline: gsap.core.Timeline;

    function t(key: string): string {
        try {
            return i18n?.t?.(key) || key;
        } catch (error) {
            console.error('Translation error:', error);
            return key;
        }
    }

    onMount(() => {
        gsap.registerPlugin(ScrollTrigger);

        // Pin the hero section
        gsap.to(".heroSection", {
            scrollTrigger: {
                trigger: ".heroSection",
                scroller: "body",
                pin: true,
                scrub: true,
            },
        });

        // Text animation timeline
        timeline = gsap.timeline();
        
        // Initial state with dot
        timeline.set(animatedText, { 
            innerHTML: `[ <span class="pulsating-dot"></span> ]`
        });
        
        // Wait for 3 seconds while dot pulsates
        timeline.to({}, { duration: 3 });
        
        // Text appears from left to right
        const finalText = t('cicero.hero.subtitle') + '.';
        const words = finalText.split(' ');
        const steps = words.length;
        
        for (let i = 0; i <= steps; i++) {
            const visibleWords = words.slice(0, i);
            const remainingSpace = " ".repeat(Math.max(1, 3));
            
            timeline.to(animatedText, {
                innerHTML: `[${remainingSpace}${visibleWords.join(' ')}${remainingSpace}]`,
                duration: 0.2,
                ease: "none"
            });
        }

        // Combined text and button animation
        const tl = gsap.timeline({
            scrollTrigger: {
                trigger: ".heroSection",
                scroller: "body",
                scrub: 1,
                start: "top 0%",
                end: "top -100%",
            }
        });

        tl.to([heroText, heroButton], {
            y: "-490%",
            opacity: 0,
            duration: 1,
            ease: "power1.inOut",
        });

        return () => {
            if (timeline) {
                timeline.kill();
            }
        };
    });
</script>

<section class="heroSection w-full h-screen flex items-center justify-center relative bg-gray-50 dark:bg-gray-900">
    <div
        bind:this={heroText}
        class="w-full max-w-[1440px] mx-auto text-center px-4"
    >
        <h1 class="w-full text-4xl sm:text-5xl md:text-6xl lg:text-7xl xl:text-[80px] leading-tight lg:leading-[80px] font-Inter font-bold uppercase text-gray-900 dark:text-gray-50">
            {t('cicero.hero.title')}
        </h1>
        <div class="mt-4 text-xl sm:text-2xl md:text-[1.875rem] font-Inter font-normal leading-[30px] bg-yellow-300/70 dark:bg-yellow-200/20 text-gray-900 dark:text-gray-50 inline-block px-4 py-2 rounded-lg">
            <span bind:this={animatedText}></span>
        </div>
    </div>

    <button
        bind:this={heroButton}
        class="absolute bottom-20 left-1/2 -translate-x-1/2 bg-gray-900 dark:bg-gray-50 text-gray-50 dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-200 px-6 py-3 font-sans text-lg font-medium leading-[20px] rounded-full uppercase transition-all duration-300 hover:scale-105"
        on:click={() => goto('/auth')}
    >
        {t('cicero.hero.cta')}
    </button>
</section>

<style>
    .pulsating-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        background-color: currentColor;
        border-radius: 50%;
        animation: pulse 1.5s infinite;
    }

    @keyframes pulse {
        0% {
            transform: scale(0.8);
            opacity: 0.5;
        }
        50% {
            transform: scale(1.2);
            opacity: 1;
        }
        100% {
            transform: scale(0.8);
            opacity: 0.5;
        }
    }
</style>
