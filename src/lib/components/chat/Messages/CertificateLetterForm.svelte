<script lang="ts">
	import { getContext, onMount, tick } from 'svelte';

	import Modal from '$lib/components/common/Modal.svelte';
	import { DateInput } from 'date-picker-svelte';
	import Textfield from '@smui/textfield';
	import { createEventDispatcher } from 'svelte';
	import { user } from '$lib/stores';
	import { submitHRDocuments } from '$lib/apis/chats';
	import { toast } from 'svelte-sonner';
	// import Select, { Option } from '@smui/select';

	const i18n = getContext('i18n');

	const dispatch = createEventDispatcher();

	let language = '';
	let purpose = '';
	let type = '';
	let addressee = '';
	const letters = [
		'Job Letter',
		'Salary Certificate',
		'Bank Letter',
		'Salary Transfer Letter',
		'NOC (No Objection Certificate)',
		'Golden Visa Application Letter'
	];

	$: if (type) {
		addressee = '';
		purpose = '';
		language = '';
	}

	const dateFormatter = (val) => {
		const date = val ? new Date(val) : new Date();
		// const dateString = date.toDateString().split(' ')
		// dateString.splice(0,1)
		// return `${dateString[1]} ${dateString[0]} ${dateString[2]}`
		const months = [
			'January',
			'February',
			'March',
			'April',
			'May',
			'June',
			'July',
			'August',
			'September',
			'October',
			'November',
			'December'
		];

		const day = date.getDate();
		const month = months[date.getMonth()];
		const year = date.getFullYear();

		// 添加后缀
		let suffix = 'th';
		if (day % 10 === 1 && day !== 11) {
			suffix = 'st';
		} else if (day % 10 === 2 && day !== 12) {
			suffix = 'nd';
		} else if (day % 10 === 3 && day !== 13) {
			suffix = 'rd';
		}

		return `${month} ${day}${suffix}, ${year}`;
	};
	const handleConfirm = () => {
		if (!$user.extra_sso) {
			toast.error('User type error. Only supports users login with outlook account.');
			return;
		}
		const ssoData = JSON.parse($user.extra_sso);
		const formData = {
			name: $user.name,
			employee_id: ssoData.emp_id,
			job_title: ssoData.job_title,
			dept: ssoData.department,
			type_of_document: letters.findIndex((el) => el == type) + 1 ?? undefined,
			purpose,
			language,
			addressee,
			email: $user.email,
			date: dateFormatter()
		};
		// dispatch('confirm', formData);
		submitHRDocuments(localStorage.token, formData)
			.then((res) => {
				dispatch('confirm', {
					...formData,
					documentName: type
				});
			})
			.catch((err) => {
				toast(err.detail + ' Submission failed.');
				return;
			});
	};
</script>

<!-- <Modal size="lg" bind:show> -->
<div class="w-7/12 bg-[#ffffffdd] dark:bg-[#ffffff80] rounded-lg my-4 mx-2 modal-content">
	<div class="flex flex-col md:flex-row w-full p-8 md:space-x-4">
		<div class=" w-full dark:text-gray-900 overflow-y-scroll scrollbar-hidden">
			<form
				on:submit|preventDefault={() => {
					handleConfirm();
				}}
			>
				<!-- Letter type  -->
				<div class="flex w-full">
					<div class="flex-1">
						<div class="mb-2 text-sm">Letter Type</div>
						<div class="flex items-center">
							<select
								required
								bind:value={type}
								class="flex-1 rounded-md px-2 h-[44px] bg-transparent"
								style="border: 1px solid #0000004D"
							>
								{#each letters as leaveType}
									<option value={leaveType}>{leaveType}</option>
								{/each}
							</select>
						</div>
					</div>
					{#if type === 'Salary Certificate'}
						<div class="flex-1 ml-6">
							<div class="mb-2 text-sm">Language</div>
							<div class="flex items-center">
								<select
									required
									bind:value={language}
									class="flex-1 rounded-md px-2 h-[44px] bg-transparent"
									style="border: 1px solid #0000004D"
								>
									{#each ['English', 'Arabic'] as lang}
										<option value={lang}>{lang}</option>
									{/each}
								</select>
							</div>
						</div>
					{/if}
				</div>

				{#if !type.includes('Golden')}
					<!-- Addressee -->
					<div class="mt-4 mb-2 text-sm">Addressee's Name</div>
					<Textfield required variant="outlined" bind:value={addressee} class="w-full" />

					<!-- Purpose  -->
					<div class="mt-4 mb-2 text-sm">Purpose of Request</div>
					<Textfield textarea required variant="outlined" bind:value={purpose} class="w-full" />
				{/if}
				<!-- Footer -->
				<div class="flex mt-8 justify-end">
					<button
						class="py-1 px-12 rounded-lg border border-black/opacity-3 text-black/opacity-60 text-sm dark:text-white"
						on:click={() => {
							// show = false;
							dispatch('cancel');
						}}>Cancel</button
					>
					<button class="py-1 px-12 ml-6 text-white bg-[#1595F4] rounded-lg text-sm" type="submit"
						>Confirm</button
					>
				</div>
			</form>
		</div>
	</div>
</div>

<!-- </Modal> -->

<style>
	.modal-content {
		animation: scaleUp 0.5s ease-out forwards;
	}

	@keyframes scaleUp {
		from {
			transform: scale(0.85);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
</style>
