import { useEffect, useRef, useState } from 'react';

interface Props {
  value: number;
  /** Render format, e.g. prefix "$" for cash. */
  format?: (n: number) => string;
  durationMs?: number;
  className?: string;
}

/**
 * Counts smoothly from its previous value to the new one whenever `value`
 * changes. Used for every metric so numbers feel alive.
 */
export default function AnimatedNumber({
  value,
  format = (n) => Math.round(n).toString(),
  durationMs = 700,
  className,
}: Props) {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef<number>();

  useEffect(() => {
    const from = fromRef.current;
    const to = value;
    if (from === to) {
      setDisplay(to);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (to - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      fromRef.current = value;
    };
  }, [value, durationMs]);

  return <span className={className}>{format(display)}</span>;
}
