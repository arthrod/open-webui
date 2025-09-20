<script lang="ts">
  import { onMount } from 'svelte';
  import { user } from '$lib/stores';
  import { logActivity } from '$lib/utils/log-activity';

  export let imageUrls = [
   '/assets/images/adam.jpg',
   '/assets/images/galaxy.jpg',
   '/assets/images/earth.jpg',
   '/assets/images/space.jpg'
  ];
  export let duration = 5000;
  export let showArrows = true;
  export let merchantName = null;
  let selectedImageIdx = 0;

  onMount(() => {
    if (imageUrls.length > 1) {
      let interval = setInterval(() => {
        nextImage();
      }, duration);

      return () => clearInterval(interval);
    }
  });

  function nextImage() {
    selectedImageIdx = (selectedImageIdx + 1) % imageUrls.length;
  }

  function prevImage() {
    selectedImageIdx = (selectedImageIdx - 1 + imageUrls.length) % imageUrls.length;
  }

  export let logoExists = false;
  $: {
    if (merchantName) {
      fetch(`/static/affiliate_logos/${merchantName}.png`, { method: 'HEAD' })
        .then(res => logoExists = res.ok)
        .catch(() => logoExists = false);
    }
  }
</script>

<div class="carousel-container">
  {#each imageUrls as imageUrl, idx (idx)}
   <div
    class="image justify-center absolute top-0 left-0 bg-cover bg-center transition-opacity duration-250"
    style="opacity: {selectedImageIdx === idx ? 1 : 0}; background-image: url('{imageUrl}')"
   ></div>
  {/each}

  <!-- Overlay an logo.png on right-top corner. If merchant-name is not empty or not null-->
  {#if merchantName}
    {#if logoExists}
      <div class="absolute top-0 right-0 p-4">
        <img src="/static/affiliate_logos/{merchantName}.png" title="Amazon Affiliate" alt="Logo" class="h-6 w-6 rounded-full border-1 border-gray-400 absolute top-1 right-1 z-20 bg-gray-100" />
      </div>
    {/if}
  {/if}

  {#if showArrows && imageUrls.length > 1}
    <!-- Left button -->
    <button
     class="absolute top-1/2 left-1 transform -translate-y-1/2 text-gray-300 text-3xl p-2"
     on:click={() => { prevImage(); logActivity(`Carousel: Moved to previous image`, $user?.id); }}
    >
     &#10094;
    </button>

    <!-- Right button -->
    <button
     class="absolute top-1/2 right-1 transform -translate-y-1/2 text-gray-300 text-3xl p-2"
     on:click={() => { nextImage(); logActivity(`Carousel: Moved to next image`, $user?.id); }}
    >
     &#10095;
    </button>
  {/if}
</div>

<style>
  .carousel-container {
   width: 100%;
   height: 100%;
  }

  .image {
   position: absolute;
   top: 0;
   left: 0;
   width: 100%;
   height: 100%;
   background-size: cover;
   background-position: center;
   transition: opacity 1s ease-in-out;
   opacity: 0;
  }

  .image:nth-child(1) {
   opacity: 1;
  }
</style>