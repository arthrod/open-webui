import { WEBUI_API_BASE_URL } from '$lib/constants';
import { fetchApi } from '$lib/utils';

export const getMessages = async (params) => {
	let error = null;

	const res = await fetchApi(`${WEBUI_API_BASE_URL}/dashboard/chats`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${localStorage.token}`
		},
		body: JSON.stringify(params)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.log(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res ? res : [];
};
