// Directional hint helpers — show DIRECTION + rough MAGNITUDE, never exact
// numbers, so the player feels uncertainty before committing.

export type Dir = '++' | '+' | '0' | '-' | '--';

export function toDir(delta: number): Dir {
  if (delta >= 6) return '++';
  if (delta >= 1) return '+';
  if (delta <= -6) return '--';
  if (delta <= -1) return '-';
  return '0';
}

export const DIR_ARROW: Record<Dir, string> = {
  '++': '▲▲',
  '+': '▲',
  '0': '•',
  '-': '▼',
  '--': '▼▼',
};

export function dirColor(d: Dir): string {
  if (d === '++' || d === '+') return 'var(--good)';
  if (d === '--' || d === '-') return 'var(--bad)';
  return 'var(--text-soft)';
}

/** Rough cash-direction from a signed cash change. */
export function cashDir(delta: number): Dir {
  if (delta >= 20000) return '++';
  if (delta > 0) return '+';
  if (delta <= -20000) return '--';
  if (delta < 0) return '-';
  return '0';
}
