<script lang="ts">
	import { userSignOut } from '$lib/apis/auths';
	import i18n from '$lib/i18n';
	import { config, endTimestamp, termsOfUse } from '$lib/stores';
	import { onMount } from 'svelte';

	const SECOND: number = 1000;
	const MINUTE: number = 60 * SECOND;

	let timeRemaining: number;

	const formatTime = (timestamp: number) => {
		const minutes = Math.floor(timestamp / MINUTE);
		const seconds = Math.floor((timestamp % MINUTE) / SECOND);
		if (minutes === 0) return `${seconds}s`;
		else if (seconds === 0) return `${minutes}min`;
		else return `${minutes}min ${seconds}s`;
	};

	onMount(() => {
		if ($endTimestamp < Date.now()) {
			// Reset timer and terms of use status
			$endTimestamp = Date.now() + ($config.features.queue.session_duration * SECOND);
			$termsOfUse.accepted = false;
			$termsOfUse.show = false;
		}

		timeRemaining = $endTimestamp - Date.now();

		const timer = setInterval(() => {
			timeRemaining = $endTimestamp - Date.now();
			if (Math.floor(timeRemaining / SECOND) <= 0) {
				console.log('entered');
				clearInterval(timer);
				userSignOut();
				$endTimestamp = -1;
				termsOfUse.reset();
				localStorage.removeItem('token');
				location.href = '/auth';
			}
		}, SECOND);
	});
</script>

<div
	class="fixed top-1.5 lg:top-3 right-1/2 translate-x-2/3 flex justify-center items-center space-x-1 lg:space-x-3 lg:bg-white lg:border px-5 py-3 rounded-lg lg:shadow-md z-50
  dark:md:bg-gray-900 dark:text-gray-200 dark:md:border-2 dark:border-gray-800 dark:shadow-none
	{timeRemaining < MINUTE ? 'md:border-red-500 lg:border-2 text-red-500 font-bold' : ''} "
>
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 -960 960 960"
		fill="currentColor"
		class="h-3 w-3 lg:h-5 lg:w-5{timeRemaining < MINUTE ? 'fill-red-500' : ''} dark:fill-gray-300"
	>
		<path
			d="M360-840v-80h240v80H360Zm80 440h80v-240h-80v240Zm40 320q-74 0-139.5-28.5T226-186q-49-49-77.5-114.5T120-440q0-74 28.5-139.5T226-694q49-49 114.5-77.5T480-800q62 0 119 20t107 58l56-56 56 56-56 56q38 50 58 107t20 119q0 74-28.5 139.5T734-186q-49 49-114.5 77.5T480-80Zm0-80q116 0 198-82t82-198q0-116-82-198t-198-82q-116 0-198 82t-82 198q0 116 82 198t198 82Zm0-280Z"
		/>
	</svg>
	<span class="text-xs lg:text-sm w-16 lg:w-48">
		<span class="max-lg:hidden">{$i18n.t('Time remaining')} : </span>
		<span> {formatTime(timeRemaining)} </span>
	</span>
</div>
