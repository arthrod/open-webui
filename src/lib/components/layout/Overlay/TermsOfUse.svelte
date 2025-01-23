<script lang="ts">
	// Imports
	import { termsOfUse } from '$lib/stores';
	import { getContext, onMount } from 'svelte';

	const i18n = getContext('i18n'); // Translations

	let termsScrolled = false;
	let popupRef: HTMLDivElement | null = null;

	// Function to check if the terms of use are fully scrolled
	const handleScroll = (event: Event) => {
		const element = event.target as HTMLDivElement;
		termsScrolled = element.scrollTop + element.clientHeight >= element.scrollHeight - 25;
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

		document.addEventListener('focusin', handleFocus);
		document.addEventListener('keydown', stickFocus);

		return () => {
			// Cleanup event listeners
			document.removeEventListener('focusin', handleFocus);
			document.removeEventListener('keydown', stickFocus);
		};
	});
</script>

{#if $termsOfUse.show}
	<div
		class="h-screen w-screen absolute backdrop-blur-[1px] backdrop:disabled z-50 bg-white/30 dark:bg-black/30"
	/>
	<!-- svelte-ignore a11y-no-noninteractive-tabindex -->
	<div
		class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-11/12 md:w-1/2 h-4/5 md:h-2/3 p-6 md:p-12 pb-4 md:pb-8 flex flex-col border shadow-xl rounded-3xl bg-white z-50
		dark:bg-gray-900 dark:text-gray-200 dark:border-gray-800 dark:border-2 dark:shadow-none"
		tabindex="0"
		bind:this={popupRef}
	>
		<div class="mb-4 md:mb-8 md:text-3xl font-bold">
			{$i18n.t('Please accept the terms of use to keep chatting')}
		</div>

		<div
			id="terms"
			class="overflow-y-auto shadow-inner border p-2 md:p-4 md:pt-3 flex flex-col space-y-4 md:space-y-6 text-xs md:text-sm text-gray-600
			dark:border-gray-800 dark:text-gray-400"
			on:scroll={handleScroll}
		>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm md:text-base"> {$i18n.t('Free Access')} </span>
				<div>
					{$i18n.t('Lucie.chat is freely available until February 15th, allowing you to explore and test the first version of the Lucie model.')}
				</div>
				<div>
					<a
						href="https://huggingface.co/collections/OpenLLM-France/lucie-llm-67099ba7b992dee2c32b1f92"
						class="hover:underline text-violet-500"
					>
						{$i18n.t('Lucie')}
					</a>
					{$i18n.t('is a fully Open Source AI model, developed by the')}
					<a href="https://www.openllm-france.fr/" class="hover:underline text-violet-500">
						{$i18n.t('OpenLLM France')}
					</a>
					{$i18n.t('community with the support of')}
					<a href="https://www.linagora.com/" class="hover:underline text-violet-500"> LINAGORA </a>
					{$i18n.t('to promote transparency and collaboration in AI innovation.')}
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm md:text-base"> {$i18n.t('Data Collection')} </span>
				<div>
					{$i18n.t('By accessing Lucie.chat for free, you agree to authorize us to collect your chat history with Lucie.')}
				</div>
				<div>{$i18n.t('The data collected will serve two key purposes:')}</div>
				<ol class="list-decimal list-inside space-y-2">
					<li>
						<span class="font-medium"> {$i18n.t('Improvement of the Lucie Model :')} </span> {$i18n.t('Your interactions help us refine and enhance Lucie\'s quality, ensuring she becomes more accurate, reliable, and useful.')}
					</li>
					<li>
						<span class="font-medium"> {$i18n.t('Contribution to Open Source Innovation :')} </span> {$i18n.t('By using Lucie.chat, you are actively contributing to the development of a 100% Open Source AI model. This initiative fosters transparency, collaboration, and accessibility in the AI ecosystem, benefiting a global community.')}
					</li>
				</ol>
				<div>
					{$i18n.t('Rest assured, all data will be handled in accordance with our strict privacy and security standards.')}
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm md:text-base"> {$i18n.t('Privacy and Security')} </span>
				<div>
					{$i18n.t('We are deeply committed to protecting your privacy and ensuring the security of your data. For more information on how your data is stored, processed, and used responsibly, please refer to our')}
					<a href="https://linagora.com/fr/privacy" class="hover:underline text-violet-500"
						>{$i18n.t('Privacy Policy')}</a
					>.
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm md:text-base"> {$i18n.t('Usage Guidelines')} </span>
				<div>
					{$i18n.t('We kindly ask that you use Lucie.chat responsibly and in compliance with applicable laws and regulations.')}
				</div>
				<div>
					{$i18n.t('Any misuse of the service, including but not limited to offensive, harmful, or unlawful behavior, is strictly prohibited.')}
				</div>
			</div>
			<div class="flex flex-col space-y-2">
				<span class="font-semibold text-sm md:text-base"> {$i18n.t('Thank You')} </span>
				<div>
					{$i18n.t('Thank you for using Lucie.chat ! We hope you enjoy exploring and testing the Lucie model while contributing to the advancement of Open Source AI.')}
				</div>
			</div>
		</div>

		<div class="mt-4 md:mt-8 self-end flex space-x-3 md:space-x-6">
			<button
				class="py-2 md:py-3 px-4 md:px-6 rounded-full text-sm md:text-base text-gray-500 hover:text-red-800 disabled:text-gray-500 disabled:cursor-not-allowed
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
				class="py-2 md:py-3 px-4 md:px-6 bg-black text-white rounded-full text-sm md:text-base hover:bg-gray-800 disabled:bg-gray-500 disabled:cursor-not-allowed
				dark:disabled:bg-gray-800 dark:disabled:text-gray-400 dark:bg-gray-700 dark:text-gray-200"
				disabled={!termsScrolled}
				on:click={() => {
					$termsOfUse.show = false;
					$termsOfUse.accepted = true;
				}}
			>
				{$i18n.t('Accept')}
			</button>
		</div>
	</div>
{/if}
