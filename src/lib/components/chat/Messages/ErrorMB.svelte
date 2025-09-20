<script lang="ts">
	import '$lib/styles/pill-button.css';
	const i18n = getContext('i18n');
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte';
	import { getContext } from 'svelte';
	import Info from '$lib/components/icons/Info.svelte'; // Import the shared styles
	export let initNewChat: Function;
	export let content = '';

</script>
<div class="flex my-2 gap-2.5 border px-4 py-3 border-red-600/10 bg-red-600/10 rounded-lg">
	<div class=" self-start mt-0.5">
		<Info className="size-5 text-red-700 dark:text-red-400" />
	</div>

	<div class=" self-center text-sm">
		{#if typeof content === 'string'}
			{content}
		{:else if typeof content === 'object' && content !== null}
			{#if content?.error && content?.error?.message}
				{content.error.message}
			{:else if content?.detail}
				{content.detail}
			{:else if content?.message}
				{content.message}
			{:else}
				{JSON.stringify(content)}
			{/if}
		{:else}
			{JSON.stringify(content)}
		{/if}
	</div>
	<button id="error-new-chat-button"
	class="pill-button transition w-max rounded-full font-medium text-sm py-1 px-4"
	on:click={() => {
		initNewChat();
	}}
	>
		<div class="flex justify-center items-center">
			<PencilSquare className="size-5 text-white" strokeWidth="2" />
		</div>
	</button>
</div>
