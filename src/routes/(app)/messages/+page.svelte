<script>
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { WEBUI_NAME, config, user } from '$lib/stores';
	import { goto } from '$app/navigation';
	import { onMount, getContext } from 'svelte';

	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';

	import { updateUserRole, getUsers, deleteUserById } from '$lib/apis/users';
	import { getMessages } from '$lib/apis/admin';
	import { getSignUpEnabledStatus, toggleSignUpEnabledStatus } from '$lib/apis/auths';
	import EditUserModal from '$lib/components/admin/EditUserModal.svelte';
	import SettingsModal from '$lib/components/admin/SettingsModal.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import UserChatsModal from '$lib/components/admin/UserChatsModal.svelte';
	import AddUserModal from '$lib/components/admin/AddUserModal.svelte';

	import { mockData } from './constants.ts';

	const i18n = getContext('i18n');

	let loaded = false;
	let messages = [];
	let users = [];

	let search = '';
	let selectedUser = null;

	let page = 1;
	let totalCount = 0;

	let showSettingsModal = false;
	let showAddUserModal = false;

	let showUserChatsModal = false;
	let showEditUserModal = false;

	let filteredReason = '';
	let filteredRating = 0;
	let filteredUser = 0;
	let filterParams = {};
	let searchType = 'title';

	let LIKE_REASONS = [];
	let DISLIKE_REASONS = [];
	let ratingReasons = [];

	$: if (page) {
		updateFilter(true);
	}

	function loadReasons(rate) {
		if (!LIKE_REASONS.length || !DISLIKE_REASONS.length) {
			LIKE_REASONS = [
				'Correct',
				$i18n.t('Accurate information'),
				$i18n.t('Followed instructions perfectly'),
				$i18n.t('Showcased creativity'),
				$i18n.t('Positive attitude'),
				$i18n.t('Attention to detail'),
				$i18n.t('Thorough explanation')
			];

			DISLIKE_REASONS = [
				'Incorrect',
				'Partially incorrect',
				$i18n.t("Don't like the style"),
				$i18n.t('Not factually correct'),
				$i18n.t("Didn't fully follow instructions"),
				$i18n.t("Refused when it shouldn't have"),
				$i18n.t('Being lazy')
			];
		}
		if (filteredRating) {
			ratingReasons = filteredRating == 1 ? [...LIKE_REASONS] : [...DISLIKE_REASONS];
		} else {
			ratingReasons = LIKE_REASONS.concat(DISLIKE_REASONS);
		}
		ratingReasons.unshift('All');
		ratingReasons.push($i18n.t('Other'));
	}

	const updateFilter = async (pageNumChange = false) => {
		if (!pageNumChange) {
			page = 1;
		}
		let params = {
			page_number: page,
			page_size: 12
		};
		if (filteredRating) {
			params.rating = filteredRating;
		}
		if (filteredReason) {
			params.rating_reason = filteredReason === 'All' ? '' : filteredReason;
		}
		if (filteredUser) {
			params.user = { id: filteredUser };
		}
		if (!!search) {
			switch (searchType) {
				case 'name':
					params.user[searchType] = search;
					break;
				default:
					params[searchType] = search;
					break;
			}
		}
		getMessages(params).then((res) => {
			if (res.total_pages == 0) {
				page = 0;
			}
			messages = [...res.chats] || [];
			totalCount = res.total_chats || 0;
		});
	};

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
		} else {
			users = await getUsers(localStorage.token);
			users.unshift({
				id: 0,
				name: 'All'
			});
		}
		loaded = true;
		loadReasons();
	});
</script>

<svelte:head>
	<title>{$i18n.t('Response Checking')} | {$WEBUI_NAME}</title>
</svelte:head>

<!-- <UserChatsModal bind:show={showUserChatsModal} user={selectedUser} />
<SettingsModal bind:show={showSettingsModal} /> -->

<div class="min-h-screen max-h-[100dvh] w-full flex justify-center dark:text-white">
	{#if loaded}
		<div class=" flex flex-col justify-between w-full overflow-y-auto">
			<div class=" mx-auto w-full">
				<div class="w-full">
					<div class=" flex flex-col justify-center">
						<div class=" px-12 pt-4">
							<div class=" flex justify-between items-center">
								<div class="flex items-center text-2xl font-semibold">User Messages</div>
								<!-- <div>
									<Tooltip content={$i18n.t('Admin Settings')}>
										<button
											class="flex items-center space-x-1 p-2 md:px-3 md:py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 transition"
											type="button"
											on:click={() => {
												showSettingsModal = !showSettingsModal;
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 16 16"
												fill="currentColor"
												class="w-4 h-4"
											>
												<path
													fill-rule="evenodd"
													d="M6.955 1.45A.5.5 0 0 1 7.452 1h1.096a.5.5 0 0 1 .497.45l.17 1.699c.484.12.94.312 1.356.562l1.321-1.081a.5.5 0 0 1 .67.033l.774.775a.5.5 0 0 1 .034.67l-1.08 1.32c.25.417.44.873.561 1.357l1.699.17a.5.5 0 0 1 .45.497v1.096a.5.5 0 0 1-.45.497l-1.699.17c-.12.484-.312.94-.562 1.356l1.082 1.322a.5.5 0 0 1-.034.67l-.774.774a.5.5 0 0 1-.67.033l-1.322-1.08c-.416.25-.872.44-1.356.561l-.17 1.699a.5.5 0 0 1-.497.45H7.452a.5.5 0 0 1-.497-.45l-.17-1.699a4.973 4.973 0 0 1-1.356-.562L4.108 13.37a.5.5 0 0 1-.67-.033l-.774-.775a.5.5 0 0 1-.034-.67l1.08-1.32a4.971 4.971 0 0 1-.561-1.357l-1.699-.17A.5.5 0 0 1 1 8.548V7.452a.5.5 0 0 1 .45-.497l1.699-.17c.12-.484.312-.94.562-1.356L2.629 4.107a.5.5 0 0 1 .034-.67l.774-.774a.5.5 0 0 1 .67-.033L5.43 3.71a4.97 4.97 0 0 1 1.356-.561l.17-1.699ZM6 8c0 .538.212 1.026.558 1.385l.057.057a2 2 0 0 0 2.828-2.828l-.058-.056A2 2 0 0 0 6 8Z"
													clip-rule="evenodd"
												/>
											</svg>

											<div class="hidden md:inline text-xs">{$i18n.t('Admin Settings')}</div>
										</button>
									</Tooltip>
								</div> -->
							</div>
						</div>

						<!-- <div class="px-6 flex text-sm gap-2.5">
							<div
								class="py-3 border-b font-medium text-gray-500 dark:text-gray-100 cursor-pointer"
							>
								Overview
							</div>
							<div class="py-3 text-gray-300 cursor-pointer">Users</div>
						</div> -->

						<hr class=" my-3 dark:border-gray-800" />

						<div class="px-12">
							<div class="mt-0.5 mb-3 gap-1 flex flex-col md:flex-row justify-between">
								<div class="flex text-lg font-medium px-0.5">
									<!-- {$i18n.t('All Users')}
									<div class="flex self-center w-[1px] h-6 mx-2.5 bg-gray-200 dark:bg-gray-700" />
									<span class="text-lg font-medium text-gray-500 dark:text-gray-300"
										>{users.length}</span
									> -->
									<div class="flex items-center rounded">
										<span class="text-sm mr-2">Filter by user</span>
										<select
											class=" dark:bg-gray-900 w-fit pr-8 rounded py-2 px-2 text-xs outline-none"
											bind:value={filteredUser}
											placeholder="Select User"
											on:change={() => {
												updateFilter();
											}}
										>
											{#each users as user}
												<option value={user.id}>{user.name}</option>
											{/each}
										</select>
									</div>
									<div class="flex items-center rounded ml-4">
										<span class="text-sm mr-2">Filter by rating</span>
										<select
											class=" dark:bg-gray-900 w-fit pr-8 rounded py-2 px-2 text-xs outline-none"
											bind:value={filteredRating}
											placeholder="Select Rating"
											on:change={() => {
												loadReasons();
												updateFilter();
											}}
										>
											<option value={0}>All</option>
											<option value={1}>👍 Good answer</option>
											<option value={-1}>👎 Bad answer</option>
										</select>
									</div>
									<div class="flex items-center px-4 rounded">
										<span class="text-sm mr-2">Filter by reason</span>
										<select
											class=" dark:bg-gray-900 w-fit pr-8 rounded py-2 px-2 text-xs outline-none"
											bind:value={filteredReason}
											on:change={() => {
												updateFilter();
											}}
										>
											{#each ratingReasons as reason}
												<option value={reason}>{reason}</option>
											{/each}
										</select>
									</div>
								</div>

								<div class="flex gap-1 text-sm items-center">
									Search by
									<select
										class=" dark:bg-gray-900 w-fit pr-8 rounded py-2 px-2 outline-none bg-transparent"
										bind:value={searchType}
										on:change={() => {}}
									>
										<!-- <option value="name">User name</option> -->
										<option value="title">Chat title</option>
										<option value="message">User Message</option>
										<option value="response">Response</option>
										<option value="rating_comment">Rating Comment</option>
									</select>
									<input
										class="w-full md:w-60 rounded-xl py-1.5 px-4 text-sm dark:text-gray-300 dark:bg-gray-850 outline-none"
										placeholder={$i18n.t('Search')}
										bind:value={search}
										on:keypress={(e) => {
											if (e.key === 'Enter') {
												updateFilter();
											}
										}}
									/>
									<button
										on:click={() => {
											updateFilter();
										}}>🔍</button
									>

									<!-- <div>
										<Tooltip content="Add User">
											<button
												class=" px-2 py-2 rounded-xl border border-gray-200 dark:border-gray-600 dark:border-0 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 transition font-medium text-sm flex items-center space-x-1"
												on:click={() => {
													showAddUserModal = !showAddUserModal;
												}}
											>
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 16 16"
													fill="currentColor"
													class="w-4 h-4"
												>
													<path
														d="M8.75 3.75a.75.75 0 0 0-1.5 0v3.5h-3.5a.75.75 0 0 0 0 1.5h3.5v3.5a.75.75 0 0 0 1.5 0v-3.5h3.5a.75.75 0 0 0 0-1.5h-3.5v-3.5Z"
													/>
												</svg>
											</button>
										</Tooltip>
									</div> -->
								</div>
							</div>

							<div class="scrollbar-hidden relative overflow-x-auto whitespace-nowrap">
								<table class="w-full text-sm text-left text-gray-500 dark:text-gray-400 table-auto">
									<thead
										class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-850 dark:text-gray-400"
									>
										<tr>
											<th scope="col" class="px-3 py-2"> {$i18n.t('Chat ID')} </th>
											<th scope="col" class="px-3 py-2"> {$i18n.t('User')} </th>
											<th scope="col" class="px-3 py-2"> {$i18n.t('Chat Title')} </th>
											<th scope="col" class="px-3 py-2">
												{$i18n.t('User Message')}
											</th>
											<th scope="col" class="px-3 py-2">
												{$i18n.t('Response')}
											</th>

											<th scope="col" class="px-3 py-2">{$i18n.t('Rating')}</th>
											<th scope="col" class="px-3 py-2">{$i18n.t('Rating Reason')}</th>
											<th scope="col" class="px-3 py-2"> {$i18n.t('Rating Comment')} </th>
											<th scope="col" class="px-3 py-2"> {$i18n.t('Chat detail')} </th>
										</tr>
									</thead>
									<tbody>
										{#each messages as msg}
											<tr class="bg-white border-b dark:bg-gray-900 dark:border-gray-700 text-xs">
												<!-- <td class="px-3 py-2 min-w-[7rem] w-28">
													<button
														class=" flex items-center gap-2 text-xs px-3 py-0.5 rounded-lg {user.role ===
															'admin' &&
															'text-sky-600 dark:text-sky-200 bg-sky-200/30'} {user.role ===
															'user' &&
															'text-green-600 dark:text-green-200 bg-green-200/30'} {user.role ===
															'pending' && 'text-gray-600 dark:text-gray-200 bg-gray-200/30'}"
														on:click={() => {
															if (user.role === 'user') {
																updateRoleHandler(user.id, 'admin');
															} else if (user.role === 'pending') {
																updateRoleHandler(user.id, 'user');
															} else {
																updateRoleHandler(user.id, 'pending');
															}
														}}
													>
														<div
															class="w-1 h-1 rounded-full {user.role === 'admin' &&
																'bg-sky-600 dark:bg-sky-300'} {user.role === 'user' &&
																'bg-green-600 dark:bg-green-300'} {user.role === 'pending' &&
																'bg-gray-600 dark:bg-gray-300'}"
														/>
														{$i18n.t(user.role)}</button
													>
												</td> -->

												<td class=" px-3 py-2 max-w-20 overflow-hidden">
													<Tooltip content={msg.id}>
														<div class="w-full overflow-hidden text-ellipsis">
															{msg.id}
														</div>
													</Tooltip>
												</td>
												<td class="px-3 py-2 font-medium text-gray-900 dark:text-white w-max">
													<div class="flex flex-row w-max">
														<!-- <img
															class=" rounded-full w-6 h-6 object-cover mr-2.5"
															src={user.profile_image_url}
															alt="user"
														/> -->

														<div class=" font-medium self-center">{msg.user.name}</div>
													</div>
												</td>
												<td class=" px-3 py-2 max-w-40 overflow-hidden">
													<Tooltip content={msg.title}>
														<div class="w-full overflow-hidden text-ellipsis">
															{msg.title}
														</div>
													</Tooltip>
												</td>
												<td class=" px-3 py-2 max-w-60 overflow-hidden text-ellipsis">
													<Tooltip content={msg.message}>
														<div class="w-full overflow-hidden text-ellipsis">
															{msg.message}
														</div>
													</Tooltip>
												</td>
												<td class=" px-3 py-2 max-w-60 overflow-hidden text-ellipsis">
													<Tooltip content={msg.response}>
														<div class="w-full overflow-hidden text-ellipsis">
															{msg.response}
														</div>
													</Tooltip>
												</td>
												<td class=" px-3 py-2"
													>{!msg.rating ? '' : msg.rating > 0 ? 'Good' : 'Bad'}</td
												>
												<td class=" px-3 py-2">{msg.rating_reason}</td>
												<td class=" px-3 py-2 max-w-40 overflow-hidden text-ellipsis">
													<Tooltip content={msg.rating_comment}>
														<div class="w-full overflow-hidden text-ellipsis">
															{msg.rating_comment}
														</div>
													</Tooltip>
												</td>
												<td class="px-3 py-2">
													<div class="flex">
														{#if msg.role !== 'admin'}
															<Tooltip content="View chat detail">
																<!-- <button
																	class="self-center w-fit text-sm px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
																	on:click={async () => {
																		showUserChatsModal = !showUserChatsModal;
																		selectedUser = user;
																	}}
																>
																	<ChatBubbles />
																</button> -->
																<a class="px-2 py-2" href="/s/{msg.id}" target="_blank">
																	<ChatBubbles />
																</a>
															</Tooltip>
														{/if}
													</div>
												</td>
											</tr>
										{/each}
									</tbody>
								</table>

								{#if !messages.length}
									<div
										class="w-full flex justify-center py-20 font-bold text-gray-700 dark:text-gray-100 text-lg"
									>
										NO DATA FOUNDED
									</div>
								{/if}
							</div>

							<!-- <div class=" text-gray-500 text-xs mt-2 text-right">
								ⓘ {$i18n.t("Click on the user role button to change a user's role.")}
							</div> -->
							{#if totalCount}
								<Pagination bind:page perPage={12} count={totalCount} />
							{/if}
						</div>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.font-mona {
		font-family: 'Mona Sans';
	}

	.scrollbar-hidden::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.scrollbar-hidden {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}
</style>
