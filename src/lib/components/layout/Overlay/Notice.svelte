<script lang="ts">
	import { showNotice } from '$lib/stores';
	import { onMount } from 'svelte';

	let noticePopupRef: HTMLDivElement | null = null; // Represents the popup element

	const closeNotice = () => {
		$showNotice = false;
	};

	const handleOverlayClick = (event: MouseEvent) => {
		if (event.target === event.currentTarget) {
			closeNotice();
		}
	};

	/**
	 * Handles key down events :
	 * Escape | Enter -> close notice
	 * Tab -> prevent focus on other page elements
	 */
	const handleKeyDown = (event: KeyboardEvent) => {
		if (!noticePopupRef) return;
		if (event.key === 'Escape' || event.key === 'Enter') {
			closeNotice();
			return;
		} else if (event.key === 'Tab') {
			const focusableElements = noticePopupRef.querySelectorAll<HTMLElement>(
				'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
			);
			const firstElement = focusableElements[0];
			const lastElement = focusableElements[focusableElements.length - 1];
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
		if (noticePopupRef) {
			noticePopupRef.focus();
		}

		// Listen to events
		document.addEventListener('keydown', handleKeyDown);
		return () => {
			document.removeEventListener('keydown', handleKeyDown);
		};
	});
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<div
	class="absolute h-full w-full flex items-center justify-center backdrop-brightness-75 backdrop-blur-sm z-50
		selection:bg-blue-500/50"
	on:click={handleOverlayClick}
>
	<button
		class="absolute top-5 right-5 text-white font-medium text-2xl cursor-pointer transition-all
			hover:text-gray-200
			max-md:hidden
			lg:right-6"
		on:click={handleOverlayClick}
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 20 20"
			fill="currentColor"
			class="w-6 h-6"
			on:click={handleOverlayClick}
		>
			<path
				d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
			/>
		</svg>
	</button>
	<div
		class="w-11/12 h-[95vh] p-6 flex flex-col space-y-4 overflow-y-scroll rounded
			bg-white/90 backdrop-blur-md shadow-md text-gray-700 text-sm text-justify
			md:h-[80vh] md:w-4/5 md:p-10 md:space-y-6 md:text-base
			xl:h- xl:w-2/3"
		bind:this={noticePopupRef}
	>
		<span class="text-xl font-medium md:text-2xl">Notice</span>
		<div class="overflow-y-scroll space-y-4">
			<div>
				Lucie est un grand modèle de langage génératif (LLM ou "large language model" en anglais),
				ce qui signifie qu'à partir d'un texte d'entrée ou d'un
				<span class="whitespace-nowrap">« prompt »</span>, il génère une réponse en rapport avec
				cette entrée. Les LLM doivent passer par de nombreuses phases d'entraînement avant de
				pouvoir répondre de manière appropriée et précise à divers prompts, et Lucie se trouve à un
				stade très précoce de son entraînement, n'ayant reçu qu'une seule série de ce que l'on
				appelle l'affinage par instruction. Cet entraînement, bien que léger, permet à Lucie de
				suivre des instructions de base, telles que répondre à une question ou résumer un texte. Ses
				réponses ne sont peut-être pas encore fiables, mais sans cet entraînement supplémentaire,
				Lucie, soumise à une instruction, ne pourrait générer que des chaînes de mots sémantiquement
				liées à cette requête. Ses réponses n'auraient pas la forme correcte.
			</div>
			<div>
				Pour passer aux étapes suivantes de l'entraînement, nous devons collecter de grandes
				quantités de données provenant d'interactions avec les utilisateurs humains. En particulier,
				nous avons besoin de savoir si une réponse fournie par Lucie est bonne, mauvaise ou
				préférable à une autre. Si nous obtenons suffisamment de données de haute qualité de ce
				type, nous pourrons les utiliser pour apprendre à Lucie à aligner ses réponses sur les
				préférences des utilisateurs humains.
			</div>
			<div>
				C'est la raison pour laquelle nous avons créé cette plateforme : pour que les utilisateurs
				puissent nous donner leur avis et nous aider à améliorer les performances de Lucie. Comme
				Lucie est entraînée sur des quantités égales de français et d'anglais (environ 33% pour
				chaque langue), nous acceptons les interactions dans les deux langues, mais nous portons un
				intérêt particulier à la collecte de données en français, car elles sont beaucoup plus
				difficiles à obtenir que les données en anglais.
			</div>
			<div>
				Gardez à l'esprit, lorsque vous interagissez avec le modèle, qu'il ne s'agit pas, et qu'il
				ne s'agira jamais, d'un ChatGPT français. Le modèle Lucie est des centaines de fois plus
				petit que les modèles à l'origine de la plateforme ChatGPT ; le convertir en un assistant
				général d'IA de ce type est tout simplement impossible. Notre intérêt est de créer un modèle
				pour aider à la génération de textes en français et en anglais et pour effectuer des tâches
				pour lesquelles les modèles de langage de base sont performants : résumer des documents,
				répondre à des questions de culture générale (en gardant à l'esprit qu'il n'a vu que des
				données jusqu'en 2023), répondre à des questions sur la base d'un texte d'entrée, écrire des
				histoires, et ainsi de suite. Il n'est pas conçu comme un assistant pour les mathématiques
				ou le codage et il n'est pas capable de fournir des conseils éthiques.
			</div>
		</div>
		<div class="flex justify-end">
			<button
				class="mt-2 px-6 py-3 rounded-full bg-blue-500 hover:bg-blue-600 text-white"
				on:click={handleOverlayClick}
			>
				Je comprends
			</button>
		</div>
	</div>
</div>
