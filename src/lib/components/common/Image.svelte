<script lang="ts">
	import { WEBUI_BASE_URL } from '$lib/constants';
	import ImagePreview from './ImagePreview.svelte';

	export let src = '';
	export let alt = '';

	export let className = ' w-full outline-hidden opacity-80 scale-85 hover:scale-125 hover:opacity-100';
	export let imageClassName = 'rounded-lg mx-auto';

	let _src = '';
	$: _src = src.startsWith('/') ? `${WEBUI_BASE_URL}${src}` : src;

	let _caption = '';
	$: _caption = alt;

	let showImagePreview = false;
</script>

<button
	class={`text-center ${className}`}
	on:click={() => {
		showImagePreview = false;
	}}
	type="button"
>
	<img src={_src} {alt} class={imageClassName} draggable="false" data-cy="image" />
	{@html _caption}
</button>

<ImagePreview bind:show={showImagePreview} src={_src} {alt} />
