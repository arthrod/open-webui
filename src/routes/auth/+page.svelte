<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { getBackendConfig } from '$lib/apis';
	import { ldapUserSignIn, getSessionUser, userSignIn, userSignUp } from '$lib/apis/auths';

	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME, config, user, socket, mobile, queueID } from '$lib/stores';

	import { generateInitialsImage, canvasPixelTest } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import OnBoarding from '$lib/components/OnBoarding.svelte';
	import { confirmConnection, getMetrics, getStatus, getTimers, joinQueue } from '$lib/apis/queue';
	import type { QueueMetrics, QueueStatus } from '$lib/apis/queue/types';
	import EyeInBox from '$lib/components/icons/EyeInBox.svelte';
	import StateGraph from '$lib/components/icons/StateGraph.svelte';
	import TouchWindow from '$lib/components/icons/TouchWindow.svelte';
	import EuLogo from '$lib/components/icons/EULogo.svelte';
	import Speedometer from '$lib/components/icons/Speedometer.svelte';
	import PlanetLeaf from '$lib/components/icons/PlanetLeaf.svelte';
	import {
		Timeline,
		TimelineItem,
		TimelineSeparator,
		TimelineDot,
		TimelineConnector,
		TimelineContent,
		TimelineOppositeContent
	} from 'svelte-vertical-timeline';
	import ContactUs from '$lib/components/layout/Overlay/ContactUs.svelte';

	const i18n = getContext('i18n');

	let loaded = false;

	let showContactUs = false;
	let queueDisabled = false;

	// Queue
	let queueStatus: QueueStatus = { position: -1, status: 'disconnected', estimated_time: 0 };
	let queueMetrics: QueueMetrics = {
		active_users: 0,
		waiting_users: 0,
		total_slots: 0
	};

	// let mode = $config?.features.enable_ldap ? 'ldap' : 'signin';
	let mode = 'queue';

	let name = '';
	let email = '';
	let password = 'password';

	let ldapUsername = '';

	const setSessionUser = async (sessionUser) => {
		if (sessionUser) {
			console.log(sessionUser);
			// toast.success($i18n.t(`You're now logged in.`));
			if (sessionUser.token) {
				localStorage.token = sessionUser.token;
			}

			$socket.emit('user-join', { auth: { token: sessionUser.token } });
			await user.set(sessionUser);
			await config.set(await getBackendConfig());
			goto('/');
		}
	};

	const signInHandler = async () => {
		const sessionUser = await userSignIn(email, password).catch((error) => {
			toast.error(error);
			return null;
		});

		await setSessionUser(sessionUser);
	};

	const signUpHandler = async () => {
		const sessionUser = await userSignUp(name, email, password, generateInitialsImage(name)).catch(
			(error) => {
				toast.error(error);
				return null;
			}
		);

		await setSessionUser(sessionUser);
	};

	const ldapSignInHandler = async () => {
		const sessionUser = await ldapUserSignIn(ldapUsername, password).catch((error) => {
			toast.error(error);
			return null;
		});
		await setSessionUser(sessionUser);
	};

	const submitHandler = async () => {
		if (mode === 'ldap') {
			await ldapSignInHandler();
		} else if (mode === 'signin') {
			await signInHandler();
		} else {
			await signUpHandler();
		}
	};

	const generateRandomStringId = (length: number = 16): string => {
		const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
		let result = '';
		const charactersLength = characters.length;
		for (let i = 0; i < length; i++) {
			result += characters.charAt(Math.floor(Math.random() * charactersLength));
		}
		return result;
	};

	// Refresh queue status periodically
	const refreshQueueStatus = async () => {
		queueStatus = await getStatus($queueID);

		if (queueStatus.status === 'waiting') {
			const refreshRatio =
				queueMetrics.waiting_users < 100
					? 100
					: queueMetrics.waiting_users < 500
						? 250
						: queueMetrics.waiting_users < 1000
							? 500
							: 1000;
			setTimeout(refreshQueueStatus, Math.max(queueStatus.position * refreshRatio, 2500));
		} else if (queueStatus.status === 'draft') {
			toast.info(
				$i18n.t('You are ready to chat with {{WEBUI_NAME}} ! Come back to the queue to start.', {
					WEBUI_NAME: $WEBUI_NAME
				})
			);
		} else if (queueStatus.status === 'connected') {
			name = `user-${$queueID}`;
			email = `${$queueID}@example.com`;
			signUpHandler();
		}
	};

	// const refreshTimer = async () => {
	// 	let timer = await getTimers($queueID);
	// 	console.log(timer);
	// 	setTimeout(refreshTimer, 1000);
	// };

	const confirmConnectionHandler = async () => {
		await confirmConnection({ user_id: $queueID });
		refreshQueueStatus();
	};

	// Join the queue and initialize periodic status refresh
	const joinQueueHandler = async () => {
		$queueID = generateRandomStringId(12);
		await joinQueue({ user_id: $queueID });

		queueMetrics = await getMetrics();

		refreshQueueStatus();
	};

	const checkOauthCallback = async () => {
		if (!$page.url.hash) {
			return;
		}
		const hash = $page.url.hash.substring(1);
		if (!hash) {
			return;
		}
		const params = new URLSearchParams(hash);
		const token = params.get('token');
		if (!token) {
			return;
		}
		const sessionUser = await getSessionUser(token).catch((error) => {
			toast.error(error);
			return null;
		});
		if (!sessionUser) {
			return;
		}
		localStorage.token = token;
		await setSessionUser(sessionUser);
	};

	let onboarding = false;

	onMount(async () => {
		if ($user !== undefined) {
			await goto('/');
		}
		await checkOauthCallback();

		// Disable joining queue if too many users are already waiting
		queueDisabled = (await getMetrics()).waiting_users >= $config.features.queue.max_waiting_users;

		loaded = true;
		if (($config?.features.auth_trusted_header ?? false) || $config?.features.auth === false) {
			// await signInHandler();
		} else {
			onboarding = $config?.onboarding ?? false;
			// if (onboarding) mode = $config?.features.enable_ldap ? 'ldap' : 'signup';
		}
	});
</script>

<svelte:head>
	<title>
		{`${$WEBUI_NAME}`}
	</title>
</svelte:head>

{#if showContactUs}
	<ContactUs bind:show={showContactUs} isLightMode={true} />
{/if}

<!-- Header -->
<div
	class="fixed w-full h-20 px-8 md:px-48 flex items-center justify-between bg-white/90 border-b-[2px] backdrop-blur-md border-gray-100 z-30"
>
	<img
		crossorigin="anonymous"
		src="/assets/logos/lucie-with-text.svg"
		class="h-full py-1"
		alt="OpenLLM France logo"
	/>
	<button
		class="h-8 md:h-14 px-3 md:px-12 rounded-full border border-black bg-white hover:bg-gray-50 text-sm md:text-base transition-all"
		on:click={() => (showContactUs = !showContactUs)}
	>
		{$i18n.t('Contact us')}
	</button>
</div>

<!-- Page -->
<div class="h-screen overflow-y-scroll pt-20 text-gray-700">
	<div class="grid md:grid-cols-2">
		<div class="p-8 md:px-48 md:py-24 flex flex-col justify-center space-y-6 bg-slate-100">
			<span class="text-2xl md:text-5xl max-md:text-center">
				{$i18n.t(
					'{{WEBUI_NAME}} — The truly open source AI built on transparency, trust, and efficiency.',
					{ WEBUI_NAME: $WEBUI_NAME }
				)}
			</span>
			<span class="text-lg md:text-2xl max-md:text-center text-gray-500">
				{$i18n.t('Beyond openness, we pioneer transparency and trust.')}
			</span>
			<div class="flex items-center md:space-x-6 max-md:flex-col max-md:space-y-8">
				{#if queueDisabled}
					<span
						class="max-md:self-center h-12 md:h-16 w-64 rounded-full bg-gray-200 text-gray-700 text-xs md:text-sm px-6 flex items-center justify-center text-center cursor-not-allowed"
					>
						{$i18n.t('Sorry, the queue is full. Please come back later.')}
					</span>
				{:else if queueStatus.status === 'disconnected'}
					<button
						class="max-md:self-center h-12 md:h-16 w-64 rounded-full bg-blue-500 hover:bg-blue-400 text-white font-medium transition-all"
						on:click={joinQueueHandler}
					>
						{$i18n.t('Try {{WEBUI_NAME}}', { WEBUI_NAME: $WEBUI_NAME })}
					</button>
				{:else if queueStatus.status === 'connected'}
					<div
						class="max-md:self-center h-12 md:h-16 w-64 flex items-center justify-center gap-3 text-lg sm:text-lg text-center font-semibold dark:text-gray-200"
					>
						<div>{$i18n.t('Signing in to {{WEBUI_NAME}}', { WEBUI_NAME: $WEBUI_NAME })}</div>

						<div>
							<Spinner />
						</div>
					</div>
				{:else if queueStatus.status === 'waiting'}
					<button
						class="max-md:self-center h-12 md:h-16 w-64 rounded-full bg-slate-400 font-medium transition-all relative"
						disabled
					>
						<span class="relative z-20 text-white">
							#{queueStatus.position}
							{$i18n.t('in queue')}
						</span>
						<span class="absolute text-xs translate-y-2 left-1/2 top-full -translate-x-1/2 w-64">
							{$i18n.t('estimated waiting time')} : ~{Math.floor(queueStatus.estimated_time / 60)}
							{$i18n.t('minutes')}
						</span>
						<div
							style="width: {Math.max(
								Math.round(
									((queueMetrics.waiting_users - queueStatus.position) /
										queueMetrics.waiting_users) *
										100
								),
								25
							)}%"
							class="absolute top-0 left-0 rounded-full h-full max-w-64 bg-slate-500 z-10 transition"
						/>
					</button>
				{:else if queueStatus.status === 'draft'}
					<button
						class="max-md:self-center h-12 md:h-16 w-64 rounded-full bg-emerald-500 hover:bg-emerald-400 text-white font-medium transition-all"
						on:click={confirmConnectionHandler}
					>
						{$i18n.t('Start chatting')}
					</button>
				{/if}
				<button
					class="h-12 md:h-16 w-64 rounded-full border border-slate-300 text-slate-500 bg-transparent hover:bg-slate-50 hover:text-slate-600 text-sm md:text-base transition-all"
					on:click={() => (showContactUs = !showContactUs)}
				>
					{$i18n.t('Contact us')}
				</button>
			</div>
			<span class="md:pt-4 text-base md:text-lg max-md:text-center">
				{$i18n.t(
					"{{WEBUI_NAME}} isn't just open, it's exceptionally transparent and reliable. From its inception, every decision has been guided by principles of trustworthiness, fairness, and accountability. Whether it's for education, government, or research, {{WEBUI_NAME}} is designed to be a model you can count on.",
					{ WEBUI_NAME: $WEBUI_NAME }
				)}
			</span>
		</div>
		<div class="max-md:p-8 max-md:pt-0 bg-white flex items-center justify-center">
			<!-- Lucie Illustration -->
			<img
				crossorigin="anonymous"
				src="/assets/images/lucie.png"
				class="md:max-h-[75vh]"
				alt="Lucie illustration"
			/>
		</div>
	</div>
	<!-- Logos -->
	<div class="px-8 md:px-48 flex flex-wrap items-center justify-center gap-8 py-8">
		<img
			crossorigin="anonymous"
			src="/assets/logos/linagora-ai.png"
			class="w-32 self-center"
			alt="Linagora AI logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/france-2030-laureat.png"
			class="w-32"
			alt="France 2030 Lauréat logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/opsci.png"
			class="h-14 self-center"
			alt="OPSCI logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/talkr-ai.png"
			class="h-14"
			alt="Talkr.ai logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/class-code.png"
			class="w-24"
			alt="Class'Code logo"
		/>
		<img crossorigin="anonymous" src="/assets/logos/cea.png" class="h-14" alt="CEA logo" />
		<img crossorigin="anonymous" src="/assets/logos/cnrs.png" class="h-14" alt="CNRS logo" />
		<img crossorigin="anonymous" src="/assets/logos/loria.png" class="h-14" alt="Loria logo" />
		<img crossorigin="anonymous" src="/assets/logos/lix.png" class="h-14" alt="LIX logo" />
		<img
			crossorigin="anonymous"
			src="/assets/logos/sorbonne.png"
			class="w-28"
			alt="Sorbonne logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/exaion.png"
			class="w-28 self-center"
			alt="Exaion logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/ovh.png"
			class="w-28 self-center bg-indigo-700 p-2 rounded-lg"
			alt="OVH Cloud logo"
		/>
		<img
			crossorigin="anonymous"
			src="/assets/logos/scaleway.svg"
			class="w-28 self-center"
			alt="Scaleway logo"
		/>
	</div>
	<div class="px-8 md:px-48 my-6 md:mt-12">
		<div class="text-2xl md:text-3xl mb-4 md:mb-8">
			{$i18n.t('Origins of the name of {{WEBUI_NAME}} model', { WEBUI_NAME: $WEBUI_NAME })}
		</div>
		<div class="flex flex-col space-y-4 text-sm md:text-base">
			<span>
				{$i18n.t(
					'{{WEBUI_NAME}} is our truly Open Source artificial intelligence, developed in collaboration with the OpenLLM-France community and supported by the French General Secretariat for Investment.',
					{ WEBUI_NAME: $WEBUI_NAME }
				)}
			</span>
			<span>
				{$i18n.t('The name {{WEBUI_NAME}} carries a dual symbolism:', { WEBUI_NAME: $WEBUI_NAME })}
			</span>
			<ol class="list-decimal list-inside space-y-2">
				<li>
					{$i18n.t(
						'It echoes "Lucy", the common ancestor of all humanity, representing universal origins and connection.'
					)}
				</li>
				<li>
					{$i18n.t(
						'It also refers to the main character of the film "Lucy" by Luc Besson, who masters all human knowledge.'
					)}
				</li>
			</ol>
			<span>
				{$i18n.t(
					'Her face is inspired by Marianne, the French Republic\'s emblem, while also reminiscent of Scarlett Johansson, the heroine of the film "Lucy". Draped in a tricolor shawl, {{WEBUI_NAME}} embodies sovereignty and French values.',
					{ WEBUI_NAME: $WEBUI_NAME }
				)}
			</span>
		</div>
	</div>
	<div class="px-8 md:px-48 my-12 md:my-24">
		<div class="text-2xl md:text-3xl mb-8 md:mb-16">
			{$i18n.t('What makes {{WEBUI_NAME}} truly Open Source ?', { WEBUI_NAME: $WEBUI_NAME })}
		</div>
		<div class="grid md:grid-cols-3 gap-12 md:gap-24 md:px-6">
			<div class="flex flex-col space-y-4 md:space-y-8">
				<EyeInBox className="size-10" />
				<span class="text-xl md:text-2xl font-medium h-16">
					{$i18n.t('Transparent Data')}
				</span>
				<span>
					{$i18n.t(
						'All training datasets are openly available and licensed for public use. We ensure transparency at every stage, from collection to curation.'
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-4 md:space-y-8">
				<StateGraph className="size-10" />
				<span class="text-xl md:text-2xl font-medium h-16">
					{$i18n.t('Open Algorithms')}
				</span>
				<span>
					{$i18n.t(
						'Our training methodologies, fine-tuning processes, and "secret sauce" are thoroughly documented and openly accessible for anyone to explore, use, and improve.'
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-4 md:space-y-8">
				<TouchWindow className="size-8" />
				<span class="text-xl md:text-2xl font-medium h-16 flex items-end">
					{$i18n.t('A Completely Free-Access Production Line')}
				</span>
				<span>
					{$i18n.t(
						"{{WEBUI_NAME}}'s weights, checkpoints, and source code are available under the Apache 2.0 license. This permissive, unrestricted license allows anyone, anywhere in the world, to use, adapt, and deploy the model for any purpose, ensuring true global accessibility and innovation.",
						{ WEBUI_NAME: $WEBUI_NAME }
					)}
				</span>
			</div>
		</div>
	</div>
	<div class="px-8 md:px-48 py-12 md:py-24 bg-gray-50">
		<div class="grid md:grid-cols-2 items-center mb-8 md:mb-16">
			<span class="text-2xl md:text-3xl">
				{$i18n.t('Designed for sovereignty and sustainability')}
			</span>
			<span class="max-md:text-sm max-md:pt-2">
				{$i18n.t(
					'{{WEBUI_NAME}} was built to address the unique challenges of developing ethical, efficient, and accessible AI.',
					{ WEBUI_NAME: $WEBUI_NAME }
				)}
			</span>
		</div>
		<div class="grid md:grid-cols-3 gap-6">
			<div class="flex flex-col space-y-4 md:space-y-8 bg-white rounded p-8">
				<EuLogo className="size-16 p-1 border-2 border-gray-700 rounded-full" />
				<span class="text-2xl md:text-3xl font-medium">{$i18n.t('European Sovereignty')}</span>
				<span>
					{$i18n.t(
						'{{WEBUI_NAME}} embodies a commitment to European values by respecting cultural diversity, promoting ethical AI development and ensuring compliance with the AI Act.',
						{ WEBUI_NAME: $WEBUI_NAME }
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-4 md:space-y-8 bg-white rounded p-8">
				<Speedometer className="size-16" />
				<span class="text-2xl md:text-3xl font-medium">{$i18n.t('Compact and Efficient')}</span>
				<span>
					{$i18n.t(
						'Optimized for low-resource environments, {{WEBUI_NAME}}\'s architecture enables deployment on "GPU poor" infrastructures and even on mobile devices.',
						{ WEBUI_NAME: $WEBUI_NAME }
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-4 md:space-y-8 bg-white rounded p-8">
				<PlanetLeaf className="size-16" />
				<span class="text-2xl md:text-3xl font-medium">{$i18n.t('Eco-Responsibility')}</span>
				<span>
					{$i18n.t(
						'By focusing on quality over quantity in training data, we ensure a lighter environmental footprint without compromising performance.'
					)}
				</span>
			</div>
		</div>
	</div>
	<div class="px-8 md:px-48 my-12 md:my-24">
		<div class="text-2xl md:text-3xl mb-8 md:mb-16">
			{$i18n.t('{{WEBUI_NAME}} in figures', { WEBUI_NAME: $WEBUI_NAME })}
		</div>
		<div class="grid grid-cols-2 md:grid-cols-5 gap-8 md:gap-24">
			<div class="flex flex-col space-y-3 md:space-y-6">
				<span class="text-xl md:text-3xl h-14 md:h-20 flex items-end">
					{$i18n.t('7 billion parameters')}
				</span>
				<div class="w-full h-px bg-black"></div>
				<span class="text-sm">
					{$i18n.t(
						'Model size: 7 billion parameters - compact and optimized for performance across diverse applications. In 2025, we will build a more compact model size of {{WEBUI_NAME}} (<3B).',
						{ WEBUI_NAME: $WEBUI_NAME }
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-3 md:space-y-6">
				<span class="text-xl md:text-3xl h-14 md:h-20 flex items-end"
					>{$i18n.t('3.1 trillion tokens')}</span
				>
				<div class="w-full h-px bg-black"></div>
				<span class="text-sm">
					{$i18n.t(
						'Training Dataset: 3.1 trillion tokens, carefully curated to balance quality and diversity, including French, English, German, Spanish, Italian, and code.'
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-3 md:space-y-6">
				<span class="text-xl md:text-3xl h-14 md:h-20 flex items-end">
					{$i18n.t('600k GPU Hours')}
				</span>
				<div class="w-full h-px bg-black"></div>
				<span class="text-sm">
					{$i18n.t(
						'Training Hours: Over 600,000 GPU hours on the Jean Zay supercomputer, utilizing 512 NVIDIA H100 GPUs in parallel.'
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-3 md:space-y-6">
				<span class="text-xl md:text-3xl h-14 md:h-20 flex items-end">
					{$i18n.t('Languages supported')}
				</span>
				<div class="w-full h-px bg-black"></div>
				<span class="text-sm">
					{$i18n.t(
						'Multilingual focus, with a primary emphasis on French and main european languages, ensuring cultural and linguistic representation.'
					)}
				</span>
			</div>
			<div class="flex flex-col space-y-3 md:space-y-6">
				<span class="text-xl md:text-3xl h-14 md:h-20 flex items-end">2023 - 2025</span>
				<div class="w-full h-px bg-black"></div>
				<span class="text-sm">
					{$i18n.t(
						"Development Timeline : Training initiated in late 2023, culminating with the model's release in January 2025."
					)}
				</span>
			</div>
		</div>
	</div>
	<!-- Timeline -->
	<div class="max-md:px-8 py-12 md:py-24 bg-gray-50 flex flex-col items-center text-center">
		<div class="text-3xl mb-8">
			{$i18n.t('Future of {{WEBUI_NAME}} in 2025', { WEBUI_NAME: $WEBUI_NAME })}
		</div>
		<div class="md:px-[33vw] mb-8 md:mb-16">
			{$i18n.t(
				"The journey of {{WEBUI_NAME}} is far from over. Our 2025 roadmap outlines ambitious milestones to enhance capabilities and expand the model's applications:",
				{ WEBUI_NAME: $WEBUI_NAME }
			)}
		</div>
		<div class="md:px-[25vw] md:-translate-x-44">
			<Timeline>
				<TimelineItem>
					<TimelineOppositeContent slot="opposite-content">
						<span class="font-bold text-base md:text-xl">Q1</span>
					</TimelineOppositeContent>
					<TimelineSeparator>
						<TimelineDot style={'background-color: transparent !important;'} />
						<TimelineConnector />
					</TimelineSeparator>
					<TimelineContent>
						<div class="flex flex-col max-md:w-52 space-y-2 pb-12">
							<span class="text-xl md:text-2xl">
								{$i18n.t('Enhanced fine-tuning and better toolkit for AI makers')}
							</span>
							<span>
								{$i18n.t(
									"We will refine {{WEBUI_NAME}}'s instruction-following capabilities (fine-instruct), introduce function calling for better integration with external systems, and release at least one model with fewer than 3 billion parameters to ensure accessibility for resource-constrained environments.",
									{ WEBUI_NAME: $WEBUI_NAME }
								)}
							</span>
						</div>
					</TimelineContent>
				</TimelineItem>
				<TimelineItem>
					<TimelineOppositeContent slot="opposite-content">
						<span class="font-bold text-base md:text-xl">Q2</span>
					</TimelineOppositeContent>
					<TimelineSeparator>
						<TimelineDot />
						<TimelineConnector />
					</TimelineSeparator>
					<TimelineContent>
						<div class="flex flex-col max-md:w-52 space-y-2 pb-12">
							<span class="text-xl md:text-2xl">
								{$i18n.t('Advanced Retrieval-Augmented Generation (RAG)')}
							</span>
							<span>
								{$i18n.t(
									'{{WEBUI_NAME}} will gain an advanced RAG function, enabling it to leverage external knowledge bases for more accurate and context-aware responses.',
									{ WEBUI_NAME: $WEBUI_NAME }
								)}
							</span>
						</div>
					</TimelineContent>
				</TimelineItem>
				<TimelineItem>
					<TimelineOppositeContent slot="opposite-content">
						<span class="font-bold text-base md:text-xl">Q3</span>
					</TimelineOppositeContent>
					<TimelineSeparator>
						<TimelineDot />
						<TimelineConnector />
					</TimelineSeparator>
					<TimelineContent>
						<div class="flex flex-col max-md:w-52 space-y-2 pb-12">
							<span class="text-xl md:text-2xl">
								{$i18n.t('Multimodal Version for {{WEBUI_NAME}}', { WEBUI_NAME: $WEBUI_NAME })}
							</span>
							<span>
								{$i18n.t(
									"We will extend {{WEBUI_NAME}}'s capabilities into multimodal AI, with a focus on voice processing in French, opening new possibilities for applications in education, accessibility, and beyond.",
									{ WEBUI_NAME: $WEBUI_NAME }
								)}
							</span>
						</div>
					</TimelineContent>
				</TimelineItem>
				<TimelineItem>
					<TimelineOppositeContent slot="opposite-content">
						<span class="font-bold text-base md:text-xl">Q4</span>
					</TimelineOppositeContent>
					<TimelineSeparator>
						<TimelineDot />
						<TimelineConnector />
					</TimelineSeparator>
					<TimelineContent>
						<div class="flex flex-col max-md:w-52 space-y-2">
							<span class="text-xl md:text-2xl"> {$i18n.t('Agentic AI Framework')} </span>
							<span>
								{$i18n.t(
									'{{WEBUI_NAME}} will evolve into a robust agentic AI framework, harnessing its capabilities to power autonomous systems and lay the foundation for Large Action Models (LAM) all while maintaining transparency, trust, and ethical safeguards.',
									{ WEBUI_NAME: $WEBUI_NAME }
								)}
							</span>
						</div>
					</TimelineContent>
				</TimelineItem>
			</Timeline>
			<!-- Styles for the timeline -->
			<style>
				.timeline {
					z-index: 0 !important;
					position: relative !important;
				}
				.timeline-dot {
					background-color: #cdcdcd !important;
					width: 20px !important;
					height: 20px !important;
					margin-bottom: 0px !important;
					margin-top: 0px !important;
					border: #cdcdcd solid 3px !important;
				}
				.timeline-connector {
					width: 3px !important;
					background-color: #cdcdcd !important;
				}
				.timeline-content,
				.timeline-opposite-content {
					margin-bottom: 0px !important;
					margin-top: 0px !important;
					transform: translateY(-7px);
				}
				@media not all and (min-width: 768px) {
					.timeline-opposite-content {
						width: 28px;
						transform: translateY(-3px);
					}
					.timeline-content {
						transform: translateY(-4px);
					}
				}
			</style>
		</div>
	</div>
	<div class="px-8 md:px-48 py-12 md:py-24">
		<div class="grid md:grid-cols-2 gap-3 md:gap-12 items-center mb-8 md:mb-16">
			<span class="text-2xl md:text-3xl">
				{$i18n.t('Join the {{WEBUI_NAME}} movement', { WEBUI_NAME: $WEBUI_NAME })}
			</span>
			<span class="text-sm leading-6">
				{$i18n.t(
					"{{WEBUI_NAME}} is more than a model - it's a community-driven effort to redefine the future of AI. By joining us, you contribute to building AI that aligns with our shared values of openness, transparency, and trust.",
					{ WEBUI_NAME: $WEBUI_NAME }
				)}
			</span>
		</div>
		<div class="grid md:grid-cols-4 gap-8">
			<div class="flex flex-col space-y-4 bg-white rounded border pb-8">
				<div
					class="h-72 p-8 flex justify-center bg-[url('/assets/design/abstract-circle.png')] bg-contain bg-no-repeat"
				>
					<img
						crossorigin="anonymous"
						src="/assets/logos/github.png"
						class="w-36 self-center"
						alt="GitHub logo"
					/>
				</div>
				<span class="md:h-16 px-8 text-xl md:text-2xl"> {$i18n.t('Collaborate on GitHub')} </span>
				<span class="px-8 text-sm max-md:pb-6 md:h-32">
					{$i18n.t("Contribute to {{WEBUI_NAME}}'s development.", { WEBUI_NAME: $WEBUI_NAME })}
				</span>
				<a
					href="https://github.com/OpenLLM-France"
					class="py-3 px-12 self-center rounded-full border border-black bg-white hover:bg-gray-50 transition-all"
				>
					{$i18n.t('Contribute')}
				</a>
			</div>
			<div class="flex flex-col space-y-4 bg-white rounded border pb-8">
				<div
					class="h-72 p-8 flex justify-center bg-[url('/assets/design/abstract-circle.png')] bg-contain bg-no-repeat"
				>
					<img
						crossorigin="anonymous"
						src="/assets/images/lucie.png"
						class="h-full w-fit self-center"
						alt="Lucie illustration"
					/>
				</div>
				<span class="md:h-16 px-8 text-xl md:text-2xl">
					{$i18n.t('Experiment on Hugging Face')}
				</span>
				<span class="px-8 text-sm max-md:pb-6 md:h-32">
					{$i18n.t("Explore {{WEBUI_NAME}}'s capabilities in your projects.", {
						WEBUI_NAME: $WEBUI_NAME
					})}
				</span>
				<a
					href="https://huggingface.co/OpenLLM-France"
					class="py-3 px-12 self-center rounded-full border border-black bg-white hover:bg-gray-50 transition-all"
				>
					{$i18n.t('Experiment')}
				</a>
			</div>
			<div class="flex flex-col space-y-4 bg-white rounded border pb-8">
				<div
					class="h-72 p-8 flex justify-center bg-[url('/assets/design/abstract-circle.png')] bg-contain bg-no-repeat"
				>
					<img
						crossorigin="anonymous"
						src="/assets/logos/openllm-france.png"
						class="w-36 self-center"
						alt="OpenLLM France Logo"
					/>
				</div>
				<span class="md:h-16 px-8 text-xl md:text-2xl"
					>{$i18n.t('Be Part of OpenLLM France')}
				</span>
				<span class="px-8 text-sm max-md:pb-6 md:h-32">
					{$i18n.t('Join the growing community dedicated to sovereign and open AI.')}
				</span>
				<a
					href="https://www.openllm-france.fr/"
					class="py-3 px-12 self-center rounded-full border border-black bg-white hover:bg-gray-50 transition-all"
				>
					{$i18n.t('Join us')}
				</a>
			</div>
			<div class="flex flex-col space-y-4 bg-white rounded border pb-8">
				<div
					class="h-72 p-8 flex justify-center bg-[url('/assets/design/abstract-circle.png')] bg-contain bg-no-repeat"
				>
					<img
						crossorigin="anonymous"
						src="/assets/logos/openllm-europe.png"
						class="w-36 self-center"
						alt="OpenLLM Europe logo"
					/>
				</div>
				<span class="md:h-16 px-8 text-xl md:text-2xl">
					{$i18n.t('Other European Initiatives')}
				</span>
				<span class="px-8 text-sm max-md:pb-6 md:h-32">
					{$i18n.t('Explore other european OpenLLM projects.')}
				</span>
				<a
					href="https://github.com/OpenLLM-Europe/European-OpenLLM-Projects"
					class="py-3 px-12 self-center rounded-full border border-black bg-white hover:bg-gray-50 transition-all"
				>
					{$i18n.t('Explore')}
				</a>
			</div>
		</div>
	</div>
	<div class="px-8 md:px-48 flex flex-col items-center space-y-6 mb-8">
		<div class="h-px w-full my-4 bg-gray-300" />
		<img
			crossorigin="anonymous"
			src="/assets/logos/openllm-france-horizontal.svg"
			class="h-16"
			alt="OpenLLM France logo"
		/>
		<div class="flex flex-col items-center space-y-2">
			<span class="text-xs">2025 - {$i18n.t('All rights reserved')} ©</span>
			<div class="text-[0.6rem]">
				<a href="https://linagora.com/fr/legal" class="underline hover:text-violet-500">
					{$i18n.t('Terms of Use')}
				</a>
				-
				<a href="https://linagora.com/fr/privacy" class="underline hover:text-violet-500">
					{$i18n.t('Privacy Policy')}
				</a>
			</div>
		</div>
	</div>
</div>
