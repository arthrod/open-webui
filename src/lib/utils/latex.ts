import katex from 'katex';
import 'katex/contrib/mhchem';
import 'katex/dist/katex.min.css';

/**
 * Renders LaTeX mathematical expressions on the page using KaTeX.
 * 
 * Searches for elements with the 'math' class and renders their content as LaTeX.
 * Elements with both 'math' and 'display' classes will be rendered in display mode.
 * 
 * @remarks
 * This function requires the KaTeX library to be loaded on the page.
 * It silently handles rendering errors and logs them to the console.
 * 
 * @example
 * ```html
 * <div class="math">x^2 + y^2 = z^2</div>
 * <div class="math display">\sum_{i=1}^n i = \frac{n(n+1)}{2}</div>
 * ```
 * ```typescript
 * renderLatex();
 * ```
 */
export function renderLatex() {
    const elements = document.getElementsByClassName('math');
    for (let i = 0; i < elements.length; i++) {
        const element = elements[i];
        try {
            const content = element.textContent || '';
            const displayMode = element.classList.contains('display');
            katex.render(content, element, {
                displayMode,
                throwOnError: false,
                output: 'html'
            });
        } catch (error) {
            console.error('Error rendering LaTeX:', error);
        }
    }
}
