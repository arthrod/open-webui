import katex from 'katex';

const DELIMITER_LIST = [
	{ left: '$$', right: '$$', display: true },
	{ left: '$', right: '$', display: false },
	{ left: '\\pu{', right: '}', display: false },
	{ left: '\\ce{', right: '}', display: false },
	{ left: '\\(', right: '\\)', display: false },
	{ left: '\\[', right: '\\]', display: true },
	{ left: '\\begin{equation}', right: '\\end{equation}', display: true }
];

// const DELIMITER_LIST = [
//     { left: '$$', right: '$$', display: false },
//     { left: '$', right: '$', display: false },
// ];

// const inlineRule = /^(\${1,2})(?!\$)((?:\\.|[^\\\n])*?(?:\\.|[^\\\n\$]))\1(?=[\s?!\.,:？！。，：]|$)/;
// const blockRule = /^(\${1,2})\n((?:\\[^]|[^\\])+?)\n\1(?:\n|$)/;

const inlinePatterns = [];
const blockPatterns = [];

/**
 * Escapes special characters in a string for use in a regular expression pattern.
 *
 * @param string - The input string to escape
 * @returns The escaped string with all RegExp special characters properly escaped
 *
 * @example
 * ```ts
 * escapeRegex("hello.world") // returns "hello\.world"
 * escapeRegex("[test]") // returns "\[test\]"
 * ```
 */
function escapeRegex(string) {
	return string.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
}

function generateRegexRules(delimiters) {
	delimiters.forEach((delimiter) => {
		const { left, right, display } = delimiter;
		// Ensure regex-safe delimiters
		const escapedLeft = escapeRegex(left);
		const escapedRight = escapeRegex(right);

		if (!display) {
			// For inline delimiters, we match everything
			inlinePatterns.push(`${escapedLeft}((?:\\\\[^]|[^\\\\])+?)${escapedRight}`);
		} else {
			// Block delimiters doubles as inline delimiters when not followed by a newline
			inlinePatterns.push(`${escapedLeft}(?!\\n)((?:\\\\[^]|[^\\\\])+?)(?!\\n)${escapedRight}`);
			blockPatterns.push(`${escapedLeft}\\n((?:\\\\[^]|[^\\\\])+?)\\n${escapedRight}`);
		}
	});

	// Math formulas can end in special characters
	const inlineRule = new RegExp(
		`^(${inlinePatterns.join('|')})(?=[\\s?。，!-\/:-@[-\`{-~]|$)`,
		'u'
	);
	const blockRule = new RegExp(`^(${blockPatterns.join('|')})(?=[\\s?。，!-\/:-@[-\`{-~]|$)`, 'u');

	return { inlineRule, blockRule };
}

const { inlineRule, blockRule } = generateRegexRules(DELIMITER_LIST);

export default function (options = {}) {
	return {
		extensions: [inlineKatex(options), blockKatex(options)]
	};
}

/**
 * Finds the starting index of a KaTeX mathematical expression in the source text.
 *
 * @param src - The source text to search for KaTeX expressions
 * @param displayMode - If true, searches for block-level math expressions; if false, searches for inline expressions
 * @returns The starting index of the first valid KaTeX expression, or undefined if none found
 *
 * @remarks
 * The function searches for KaTeX delimiters based on the display mode:
 * - Inline mode: Expressions between single or double dollar signs
 * - Display mode: Expressions between double dollar signs or \[ \] pairs
 *
 * The function validates that:
 * 1. The delimiter is either at the start of the text or preceded by whitespace/punctuation
 * 2. The expression matches the expected KaTeX syntax pattern
 */
function katexStart(src, displayMode: boolean) {
	const ruleReg = displayMode ? blockRule : inlineRule;

	let indexSrc = src;

	while (indexSrc) {
		let index = -1;
		let startIndex = -1;
		let startDelimiter = '';
		let endDelimiter = '';
		for (const delimiter of DELIMITER_LIST) {
			if (delimiter.display !== displayMode) {
				continue;
			}

			startIndex = indexSrc.indexOf(delimiter.left);
			if (startIndex === -1) {
				continue;
			}

			index = startIndex;
			startDelimiter = delimiter.left;
			endDelimiter = delimiter.right;
		}

		if (index === -1) {
			return;
		}

		// Check if the delimiter is preceded by a special character.
		// If it does, then it's potentially a math formula.
		const f = index === 0 || indexSrc.charAt(index - 1).match(/[\s?。，!-\/:-@[-`{-~]/);
		if (f) {
			const possibleKatex = indexSrc.substring(index);

			if (possibleKatex.match(ruleReg)) {
				return index;
			}
		}

		indexSrc = indexSrc.substring(index + startDelimiter.length).replace(endDelimiter, '');
	}
}

/**
 * Tokenizes KaTeX mathematical expressions in text.
 *
 * @param src - The source text to parse for KaTeX expressions
 * @param tokens - The current array of tokens (unused in current implementation)
 * @param displayMode - Whether to parse block-level (true) or inline (false) KaTeX
 * @returns An object containing the parsed KaTeX token information, or undefined if no match
 *          Properties include:
 *          - type: 'blockKatex' or 'inlineKatex'
 *          - raw: The complete matched text
 *          - text: The extracted KaTeX expression
 *          - displayMode: The display mode boolean value
 */
function katexTokenizer(src, tokens, displayMode: boolean) {
    const ruleReg = displayMode ? blockRule : inlineRule;
    const type = displayMode ? 'blockKatex' : 'inlineKatex';

    const match = src.match(ruleReg);

    if (match) {
        const text = match
            .slice(2)
            .filter((item) => item)
            .find((item) => item.trim());

        return {
            type,
            raw: match[0],
            text: text,
            displayMode
        };
    }
}

function inlineKatex(options) {
	return {
		name: 'inlineKatex',
		level: 'inline',
		start(src) {
			return katexStart(src, false);
		},
		tokenizer(src, tokens) {
			return katexTokenizer(src, tokens, false);
		}
	};
}

function blockKatex(options) {
	return {
		name: 'blockKatex',
		level: 'block',
		start(src) {
			return katexStart(src, true);
		},
		tokenizer(src, tokens) {
			return katexTokenizer(src, tokens, true);
		}
	};
}
