/**
 * Display shim for the pre-voice-fix corpus (releases 0002–0004): the first
 * logged sets address the acts by internal id ("Rust", "Keep", "Silt")
 * because the kernel didn't know the stage names yet (fixed in PR #20 —
 * personas now first-name each other: Delta / Roan / Evers). The append-only
 * log is never edited; display surfaces normalize internal act ids used as
 * PROPER NOUNS in quoted generated text to first names.
 *
 * Rules (see DECISIONS.md):
 *   - CAPITALIZED, word-boundary matches only: "Rust"→"Roan", "Keep"→"Evers",
 *     "Silt"→"Delta". Possessives carry over ("Rust's"→"Roan's",
 *     "Keep's"→"Evers's").
 *   - Common-noun/verb uses are lowercase in the corpus ("under enough silt
 *     to hold weight", "keep the hum") and are NEVER touched.
 *   - Ambiguous capitalized uses (e.g. a sentence-start imperative "Keep the
 *     hum going", or a title punning on the material like "Silt Over Silt")
 *     are handled by the curated EXCEPTION list below — every substitution in
 *     the shipped corpus was human-reviewed, so the list is exact phrases,
 *     not heuristics.
 *
 * Pure, dependency-free ESM so both the node scripts (compile_timeline.mjs,
 * normalize_names.mjs) and the web app can import it.
 */

/** Internal act id -> the first name the acts use for each other. */
export const ACT_FIRST_NAMES = { silt: "Delta", rust: "Roan", keep: "Evers" };

const NAME_BY_ID_CAP = { Rust: "Roan", Keep: "Evers", Silt: "Delta" };

/**
 * Curated exceptions: exact phrases (case-sensitive) inside which a
 * capitalized act id is NOT a proper-noun reference to the act and must be
 * left alone. Curated by human review of every substitution in the
 * pre-voice-fix corpus (see the PR table); currently none were needed —
 * "Silt Over Silt" (the Critic's take title, punning on the material) is a
 * title field, which this shim is never applied to. The list stays so a
 * future ambiguous quote has somewhere to go.
 * @type {string[]}
 */
export const EXCEPTIONS = [];

const PATTERN = /\b(Rust|Keep|Silt)(['’]s)?\b/g;

/**
 * Normalize internal act ids used as proper nouns in quoted generated text
 * to the acts' first names. Lowercase uses are never touched.
 * @param {string} text
 * @returns {string}
 */
export function normalizeActNames(text) {
  if (typeof text !== "string" || text.length === 0) return text;
  const excluded = exceptionSpans(text);
  return text.replace(PATTERN, (match, name, possessive, offset) => {
    if (excluded.some(([start, end]) => offset >= start && offset < end)) return match;
    return NAME_BY_ID_CAP[name] + (possessive ?? "");
  });
}

/** @param {string} text @returns {[number, number][]} spans covered by EXCEPTIONS */
function exceptionSpans(text) {
  const spans = [];
  for (const phrase of EXCEPTIONS) {
    let from = 0;
    for (let i; (i = text.indexOf(phrase, from)) !== -1; from = i + phrase.length) {
      spans.push([i, i + phrase.length]);
    }
  }
  return spans;
}
