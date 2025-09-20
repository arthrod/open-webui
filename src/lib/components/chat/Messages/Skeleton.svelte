<script lang="ts">
 	import { WEBUI_BASE_URL } from '$lib/constants';
	console.log(WEBUI_BASE_URL)
 	const metaThemeColorTag = document.querySelector('meta[name="theme-color"]');
 	let SRC = `${WEBUI_BASE_URL}/static/chat-waiting-mb-dark.gif`;
 	if (metaThemeColorTag?.content) {
 		if (metaThemeColorTag.content === '#ffffff') {
 			SRC = `${WEBUI_BASE_URL}/static/chat-waiting-mb-light.gif`;
 		}
 	}
</script>

<img
 	crossorigin="anonymous"
 	src="{SRC}"
 	class="w-20 h-10"
 	alt="Loading..."
 />
