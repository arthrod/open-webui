<script lang="ts">

    import { toast } from 'svelte-sonner';

    export let show = false;

    interface Contact {
        first_name: string;
        last_name: string;
        company: string;
        position: string;
        email: string;
        phone: string;
        message: string;
    }

	const validateEmailFormat = (email: string): boolean => {
		const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
		return emailRegex.test(email);
	};

	const validateForm = (
		firstName: string,
		lastName: string,
		email: string,
		message: string
	): boolean => {
		return firstName !== '' && lastName !== '' && email !== '' && message !== '';
	};

	function submitForm(event: Event) {
		event.preventDefault();

        		// Parse form data

        const contact: Contact = {
            first_name: (document.getElementById('firstname') as HTMLInputElement).value,
            last_name: (document.getElementById('lastname') as HTMLInputElement).value,
            company: (document.getElementById('company') as HTMLInputElement).value,
            position: (document.getElementById('position') as HTMLInputElement).value,
            email: (document.getElementById('email') as HTMLInputElement).value,
            phone: (document.getElementById('phone') as HTMLInputElement).value,
            message: (document.getElementById('message') as HTMLInputElement).value
        }
		if (!validateForm(contact.first_name, contact.last_name, contact.email, contact.message)) {
			toast.error('Please fill out the required (*) fields.');
			return;
		}
		if (!validateEmailFormat(contact.email)) {
			toast.error('Invalid email address.');
			return;
		}

        console.log(contact);

        // Send form to /contact api
        fetch('/contact/contact', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(contact),
        })
            .then((response) => {
                if (response.ok) {
                    console.log('Form submitted successfully');
                } else {
                    console.error('Form submission failed');
                }
            })
            .catch((error) => {
                console.error('Form submission failed', error);
            });
            
        closeModal();
	}

	function closeModal() {
		show = false;
	}

	function handleOverlayClick(event: MouseEvent) {
		if (event.target === event.currentTarget) {
			closeModal();
		}
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			closeModal();
		}
	}
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
{#if show}
	<!-- svelte-ignore a11y-no-noninteractive-tabindex -->
	<div
		class="fixed inset-0 flex items-center justify-center modal-overlay"
		on:click={handleOverlayClick}
		on:keydown={handleKeyDown}
		tabindex="0"
	>
		<form
			class="form-container shadow-md rounded px-8 pt-6 pb-8 mb-4 grid grid-cols-2 gap-4"
			on:submit={submitForm}
		>
			<div class="col-span-1">
				<label class="block text-sm font-bold mb-2 required" for="firstname"> First name </label>
				<input
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="firstname"
					type="text"
					placeholder="John"
				/>
			</div>
			<div class="col-span-1">
				<label class="block text-sm font-bold mb-2 required" for="lastname"> Last name </label>
				<input
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="lastname"
					type="text"
					placeholder="Smith"
				/>
			</div>
			<div class="col-span-1">
				<label class="block text-sm font-bold mb-2" for="company"> Company </label>
				<input
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="company"
					type="text"
					placeholder="John Smith & Co"
				/>
			</div>
			<div class="col-span-1">
				<label class="block text-sm font-bold mb-2" for="position"> Position </label>
				<input
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="position"
					type="text"
					placeholder="AI Researcher"
				/>
			</div>
			<div class="col-span-2">
				<label class="block text-sm font-bold mb-2 required" for="email"> Email adress </label>
				<input
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="email"
					type="text"
					placeholder="johnsmith@jsco.com"
				/>
			</div>
			<div class="col-span-2">
				<label class="block text-sm font-bold mb-2" for="phone"> Phone number </label>
				<input
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="phone"
					type="text"
					placeholder="+33 1 02 03 04 05"
				/>
			</div>
			<div class="col-span-2">
				<label class="block text-md font-bold mb-2 required" for="message"> Message </label>
				<textarea
					class="form-input shadow appearance-none border rounded w-full py-2 px-3 leading-tight focus:outline-none focus:shadow-outline"
					id="message"
					rows="4"
					placeholder="Your message"
				></textarea>
			</div>
			<div class="col-span-2">
				<button
					type="submit"
					class="form-button mt-4 w-full inline-flex justify-center py-3 px-4 border border-transparent shadow-sm text-sm font-medium rounded-3xl focus:outline-none focus:ring-2 focus:ring-offset-2"
				>
					Submit
				</button>
			</div>
		</form>
	</div>
{/if}

<style>
	:root {
		--background-color: white;
		--text-color: #333;
		--input-background: #fff;
		--input-border: #ccc;
		--button-background: #1d4ed8;
		--button-hover-background: #1e40af;
		--button-text-color: white;
	}

	@media (prefers-color-scheme: dark) {
		:root {
			--background-color: #333;
			--text-color: #ddd;
			--input-background: #444;
			--input-border: #555;
			--button-background: #2563eb;
			--button-hover-background: #1d4ed8;
			--button-text-color: white;
		}
	}

	.modal-overlay {
		background-color: rgba(0, 0, 0, 0.5);
	}

	.form-container {
		background-color: var(--background-color);
		color: var(--text-color);
	}

	.form-input {
		background-color: var(--input-background);
		border-color: var(--input-border);
		color: var(--text-color);
	}

	.form-button {
		background-color: var(--button-background);
		color: var(--button-text-color);
	}

	.form-button:hover {
		background-color: var(--button-hover-background);
	}

	label.required::after {
		content: ' *';
		color: #b91c1c;
	}
</style>
