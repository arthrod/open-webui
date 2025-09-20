<script lang="ts">
    import Carousel from '$lib/components/common/Carousel.svelte';
    import { createEventDispatcher } from 'svelte';

    export let product: any;

    const dispatch = createEventDispatcher();

    function handleClose() {
        dispatch('close');
    }
</script>

<div
    class="modal"
    role="dialog"
    tabindex="0"
    aria-modal="true"
    on:click={handleClose}
    on:keydown={(e) => e.key === 'Escape' && handleClose()}
>
    <div
        class="relative items-center justify-center h-[400px] w-[400px] border-1 rounded-lg bg-white"
        on:click|stopPropagation
        tabindex="0"
        role="document"
        on:keydown={(e) => e.key === 'Escape' && handleClose()}
    >
        <button
            class="close-button px-1 py-1 rounded-sm bg-gray-50 border-gray-50 text-gray-700 shadow-md z-10"
            on:click={handleClose}
        >
            <div class="m-auto self-center">
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    stroke-width="2.5"
                    class="size-3.5"
                >
                    <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        d="M6 6l12 12M6 18L18 6"
                    />
                </svg>
            </div>
        </button>
        <Carousel imageUrls={product?.thumbnails} showArrows={true} duration={3000} merchantName={product?.merchant_name}/>
    </div>
</div>

<style>
    .modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }
    .close-button {
        position: absolute;
        display: flex;
        cursor: pointer;
        top: 0;
        left: 0;
    }
</style>