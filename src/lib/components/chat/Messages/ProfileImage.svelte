<script lang="ts">
	import { WEBUI_URL } from '$lib/constants';

	export let className = 'size-8';
	export let src = `${WEBUI_URL}/static/favicon.png`;
</script>

<img
	crossorigin="anonymous"
	src={src === ''
		? `${WEBUI_URL}/static/favicon.png`
		: src.startsWith(WEBUI_URL) ||
			  src.startsWith('https://www.gravatar.com/avatar/') ||
			  src.startsWith('data:') ||
			  src.startsWith('/')
			? src
			: `${WEBUI_URL}/user.png`}
	class=" {className} object-cover rounded-full -translate-y-[1px]"
	alt="profile"
	draggable="false"
/>
