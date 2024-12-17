import { copyToClipboard } from './index';
import { toast } from 'svelte-sonner';

/**
 * Creates "Copy" buttons for all code blocks on the page.
 * 
 * Adds a button to each `<pre><code>` element that allows users to copy
 * the code block's content to their clipboard. The button appears in the
 * top-right corner of each code block.
 * 
 * @remarks
 * - Only adds buttons to code blocks that don't already have one
 * - Shows visual feedback when code is copied
 * - Automatically resets button text after 2 seconds
 * - Requires the code blocks to be wrapped in a `<pre>` element
 * 
 * @example
 * ```typescript
 * // Call once when the page loads
 * createCopyCodeBlockButton();
 * ```
 * 
 * @throws Will not throw, but silently fails if:
 * - Container element is not found
 * - Code block is empty
 * - Clipboard API is not available
 */
export function createCopyCodeBlockButton() {
    const codeBlocks = document.querySelectorAll('pre code');
    codeBlocks.forEach((codeBlock) => {
        const container = codeBlock.parentElement;
        if (!container) return;

        // Check if button already exists
        if (container.querySelector('.copy-button')) return;

        const button = document.createElement('button');
        button.className = 'copy-button absolute right-2 top-2 p-1 rounded text-sm bg-gray-700 hover:bg-gray-600 text-white';
        button.textContent = 'Copy';

        button.addEventListener('click', async () => {
            const code = codeBlock.textContent || '';
            await copyToClipboard(code);
            button.textContent = 'Copied!';
            toast.success('Code copied to clipboard');
            setTimeout(() => {
                button.textContent = 'Copy';
            }, 2000);
        });

        // Make container relative for absolute positioning of button
        container.style.position = 'relative';
        container.appendChild(button);
    });
}
