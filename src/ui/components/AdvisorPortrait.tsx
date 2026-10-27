import { motion } from 'framer-motion';
import type { Expression } from '../../engine/types';

// ============================================================================
// Procedural advisor portrait — an animated SVG face with four expressions.
// Fully self-contained (no image assets needed to play).
//
// CUSTOM ART hook: to use real illustrations, import the four images per
// department (see content/characters/<industry>/README.md) and render an <img>
// here instead of the SVG when a matching asset exists.
// ============================================================================

interface Props {
  expression: Expression;
  color: string;
  size?: number;
  /** Animate a reaction bounce (used when previewing an option). */
  reacting?: boolean;
}

const MOUTHS: Record<Expression, string> = {
  // path for the mouth, drawn in a 100x100 viewbox
  happy: 'M32 60 Q50 78 68 60',
  neutral: 'M36 64 L64 64',
  worried: 'M34 66 Q50 54 66 66',
  angry: 'M34 68 Q50 58 66 68',
};

const BROWS: Record<Expression, { l: string; r: string }> = {
  happy: { l: 'M28 38 Q34 35 40 37', r: 'M60 37 Q66 35 72 38' },
  neutral: { l: 'M28 38 L40 38', r: 'M60 38 L72 38' },
  worried: { l: 'M28 36 Q34 40 40 38', r: 'M60 38 Q66 40 72 36' },
  angry: { l: 'M28 34 L40 40', r: 'M60 40 L72 34' },
};

export default function AdvisorPortrait({
  expression,
  color,
  size = 72,
  reacting = false,
}: Props) {
  const brow = BROWS[expression];
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      initial={false}
      animate={reacting ? { scale: [1, 1.12, 1], rotate: [0, -3, 3, 0] } : { scale: 1 }}
      transition={{ duration: 0.5 }}
      aria-label={`advisor feeling ${expression}`}
    >
      <defs>
        <radialGradient id={`g-${color.replace('#', '')}`} cx="40%" cy="35%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} />
        </radialGradient>
      </defs>
      {/* head */}
      <circle cx="50" cy="52" r="44" fill={`url(#g-${color.replace('#', '')})`} stroke="rgba(0,0,0,0.25)" strokeWidth="2" />
      {/* eyes */}
      <circle cx="37" cy="50" r={expression === 'happy' ? 4.5 : 4} fill="#1b1230" />
      <circle cx="63" cy="50" r={expression === 'happy' ? 4.5 : 4} fill="#1b1230" />
      {/* eye glints */}
      <circle cx="38.5" cy="48.5" r="1.4" fill="#fff" />
      <circle cx="64.5" cy="48.5" r="1.4" fill="#fff" />
      {/* brows */}
      <path d={brow.l} stroke="#1b1230" strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d={brow.r} stroke="#1b1230" strokeWidth="3" fill="none" strokeLinecap="round" />
      {/* mouth */}
      <motion.path
        d={MOUTHS[expression]}
        stroke="#1b1230"
        strokeWidth="3.5"
        fill="none"
        strokeLinecap="round"
        initial={false}
        animate={{ d: MOUTHS[expression] }}
        transition={{ duration: 0.3 }}
      />
      {/* angry cheek flush */}
      {expression === 'angry' && (
        <>
          <circle cx="26" cy="60" r="5" fill="#ef4444" opacity="0.5" />
          <circle cx="74" cy="60" r="5" fill="#ef4444" opacity="0.5" />
        </>
      )}
    </motion.svg>
  );
}
