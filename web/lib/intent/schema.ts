import { z } from "zod";

/**
 * Intent — the 7-axis sonic palette a player carries into a set, plus the
 * era scale a release sits on. Ported from afar_music's Creative DNA; here
 * it describes what an agent is REACHING FOR, not what a human designed.
 *
 * Bipolar axes are signed −1..1: the SIGN says which pole (−1 = left/first-named
 * pole, +1 = right pole), the MAGNITUDE says how hard. 0 is neutral.
 */

export const ERAS = [
  "far-past",
  "1950s",
  "1960s",
  "1970s",
  "1980s",
  "1990s",
  "2000s",
  "2010s",
  "2020s",
  "2030s",
  "far-future",
] as const;

const signedAxis = z.number().min(-1).max(1);

/** 7 bipolar axes. −1 = first pole, +1 = second pole. */
export const SonicPaletteSchema = z.object({
  pristineLofi: signedAxis, // pristine ←→ lo-fi
  sparseDense: signedAxis, // sparse ←→ dense
  coldWarm: signedAxis, // cold ←→ warm
  improvisedStructured: signedAxis, // improvised ←→ structured
  loudQuiet: signedAxis, // loud ←→ quiet
  organicSynthetic: signedAxis, // organic ←→ synthetic
  darkHopeful: signedAxis, // dark ←→ hopeful
});

export type SonicPalette = z.infer<typeof SonicPaletteSchema>;
export type SonicAxis = keyof SonicPalette;
