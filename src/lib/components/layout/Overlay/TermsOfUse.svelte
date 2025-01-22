<script lang="ts">
	// Imports
	import { termsOfUse } from '$lib/stores';
	import { afterUpdate, getContext, onMount } from 'svelte';

	const i18n = getContext('i18n'); // Translations

	let termsScrolled = false; // true if the terms of use have been scrolled all the way to the bottom
	let popupRef: HTMLDivElement | null = null; // Represents the popup element

	// Function to check if the terms of use are fully scrolled
	const handleScroll = (event: { target: EventTarget | null }) => {
		if (!termsScrolled) {
			const terms = event.target as HTMLDivElement;
			termsScrolled = terms.scrollTop + terms.clientHeight >= terms.scrollHeight - 10;
		}
	};

	// Stick focus within the popup
	const stickFocus = (event: KeyboardEvent) => {
		if (!popupRef) return;

		const focusableElements = popupRef.querySelectorAll<HTMLElement>(
			'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
		);
		const firstElement = focusableElements[0];
		const lastElement = focusableElements[focusableElements.length - 1];

		if (event.key === 'Tab') {
			if (event.shiftKey && document.activeElement === firstElement) {
				// Shift + Tab pressed on the first element
				lastElement.focus();
				event.preventDefault();
			} else if (!event.shiftKey && document.activeElement === lastElement) {
				// Tab pressed on the last element
				firstElement.focus();
				event.preventDefault();
			}
		}
	};

	onMount(() => {
		// Focus the popup container
		if (popupRef) {
			popupRef.focus();
		}

		// Prevent focus on other elements
		const handleFocus = (event: FocusEvent) => {
			if (popupRef && !popupRef.contains(event.target as Node)) {
				event.preventDefault();
				popupRef.focus();
			}
		};

		// Listen to events
		document.addEventListener('focusin', handleFocus);
		document.addEventListener('keydown', stickFocus);

		return () => {
			// Cleanup event listeners
			document.removeEventListener('focusin', handleFocus);
			document.removeEventListener('keydown', stickFocus);
		};
	});

	afterUpdate(() => {
		// Ensures that the buttons become available if the terms are not scrollable (i.e. on large screens)
		const terms = document.getElementById('terms') as HTMLDivElement;
		if (terms) handleScroll({ target: terms });
	});
</script>

{#if $termsOfUse.show}
	<div
		class="h-screen w-screen absolute backdrop-blur-[1px] backdrop:disabled z-50 bg-white/30 dark:bg-black/30"
	/>
	<!-- svelte-ignore a11y-no-noninteractive-tabindex -->
	<div
		class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-11/12 h-4/5 p-6 pb-4 flex flex-col border shadow-xl rounded-3xl bg-white z-50
		sm:w-3/4 sm:h-3/4
		lg:w-1/2 lg:h-2/3 lg:p-12 lg:pb-8
		dark:bg-gray-900 dark:text-gray-200 dark:border-gray-800 dark:border-2 dark:shadow-none"
		tabindex="0"
		bind:this={popupRef}
	>
		<div class="mb-4 lg:mb-8 lg:text-3xl font-bold">
			{$i18n.t('Please accept the terms of use to keep chatting')}
		</div>

		<div
			id="terms"
			class="overflow-y-auto shadow-inner border p-2 lg:p-4 lg:pt-3 flex flex-col space-y-4 lg:space-y-6 text-xs lg:text-sm text-gray-600
			dark:border-gray-800 dark:text-gray-400"
			on:scroll={handleScroll}
		>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm lg:text-base"> Free Access </span>
				<div>
					Lucie.chat is freely available until February 15th, allowing you to explore and test the
					first version of the Lucie model.
				</div>
				<div>
					<a
						href="https://huggingface.co/collections/OpenLLM-France/lucie-llm-67099ba7b992dee2c32b1f92"
						class="hover:underline text-violet-500"
					>
						Lucie
					</a>
					is a fully Open Source AI model, developed by the
					<a href="https://www.openllm-france.fr/" class="hover:underline text-violet-500">
						OpenLLM France
					</a>
					community with the support of
					<a href="https://www.linagora.com/" class="hover:underline text-violet-500"> LINAGORA </a>
					to promote transparency and collaboration in AI innovation.
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm lg:text-base"> Data Collection </span>
				<div>
					By accessing Lucie.chat for free, you agree to authorize us to collect your chat history
					with Lucie.
				</div>
				<div>The data collected will serve two key purposes:</div>
				<ol class="list-decimal list-inside space-y-2">
					<li>
						<span class="font-medium"> Improvement of the Lucie Model : </span> Your interactions help
						us refine and enhance Lucie's quality, ensuring she becomes more accurate, reliable, and
						useful.
					</li>
					<li>
						<span class="font-medium"> Contribution to Open Source Innovation : </span> By using Lucie.chat,
						you are actively contributing to the development of a 100% Open Source AI model. This initiative
						fosters transparency, collaboration, and accessibility in the AI ecosystem, benefiting a
						global community.
					</li>
				</ol>
				<div>
					Rest assured, all data will be handled in accordance with our strict privacy and security
					standards.
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm lg:text-base"> Privacy and Security </span>
				<div>
					We are deeply committed to protecting your privacy and ensuring the security of your data.
					For more information on how your data is stored, processed, and used responsibly, please
					refer to our
					<a href="https://linagora.com/fr/privacy" class="hover:underline text-violet-500"
						>Privacy Policy</a
					>.
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm lg:text-base"> Usage Guidelines </span>
				<div>
					We kindly ask that you use Lucie.chat responsibly and in compliance with applicable laws
					and regulations.
				</div>
				<div>
					Any misuse of the service, including but not limited to offensive, harmful, or unlawful
					behavior, is strictly prohibited.
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm lg:text-base"> Thank You </span>
				<div>
					Thank you for using Lucie.chat ! We hope you enjoy exploring and testing the Lucie model
					while contributing to the advancement of Open Source AI.
				</div>
			</div>
		</div>

		<div
			class="mt-4 lg:mt-8 h-24 w-full flex justify-end items-center space-x-3 lg:space-x-6 group"
		>
			{#if !termsScrolled}
				<span class="grow text-sm lg:text-base lg:text-right text-red-400">
					ⓘ Please read the terms of use to continue.
				</span>
			{:else}
				<button
					class="py-2 lg:py-3 px-4 lg:px-6 rounded-full text-sm lg:text-base text-gray-500 hover:text-red-800 disabled:text-gray-500 disabled:cursor-not-allowed
			dark:disabled:text-gray-700 dark:text-gray-600"
					disabled={!termsScrolled}
					on:click={() => {
						$termsOfUse.show = false;
						$termsOfUse.accepted = false;
					}}
				>
					{$i18n.t('Decline')}
				</button>
				<button
					class="py-2 lg:py-3 px-4 lg:px-6 bg-black text-white rounded-full text-sm lg:text-base hover:bg-gray-800 disabled:bg-gray-500 disabled:cursor-not-allowed
			dark:disabled:bg-gray-800 dark:disabled:text-gray-400 dark:bg-gray-700 dark:text-gray-200"
					disabled={!termsScrolled}
					on:click={() => {
						$termsOfUse.show = false;
						$termsOfUse.accepted = true;
					}}
				>
					{$i18n.t('Accept')}
				</button>
			{/if}
		</div>
	</div>
{/if}
