import { motion } from 'framer-motion';
import type { DepartmentDef } from '../../engine/types';
import AnimatedNumber from './AnimatedNumber';

interface Props {
  def: DepartmentDef;
  performance: number;
  morale: number;
  /** Optional deltas being applied right now → drives pulse/▲▼ feedback. */
  perfDelta?: number;
  moraleDelta?: number;
  compact?: boolean;
}

function Gauge({
  label,
  value,
  delta,
}: {
  label: string;
  value: number;
  delta?: number;
}) {
  const d = delta ?? 0;
  const positive = d > 0;
  const big = Math.abs(d) >= 6;
  return (
    <div className="mb-1.5 last:mb-0">
      <div className="flex items-center justify-between text-[11px] text-[var(--text-soft)]">
        <span>{label}</span>
        <span className="flex items-center gap-1 tabular-nums">
          <AnimatedNumber value={value} />
          {d !== 0 && (
            <motion.span
              initial={{ opacity: 0, y: positive ? 6 : -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="font-semibold"
              style={{ color: positive ? 'var(--good)' : 'var(--bad)' }}
            >
              {positive ? '▲' : '▼'}
              {Math.abs(Math.round(d))}
            </motion.span>
          )}
        </span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-[var(--surface-2)]">
        <motion.div
          className="h-full rounded-full"
          style={{
            background: positive
              ? 'linear-gradient(90deg, var(--accent), var(--good))'
              : d < 0
                ? 'linear-gradient(90deg, var(--warn), var(--bad))'
                : 'linear-gradient(90deg, var(--primary), var(--accent))',
          }}
          animate={{
            width: `${value}%`,
            ...(big ? { boxShadow: ['0 0 0px', '0 0 14px var(--accent)', '0 0 0px'] } : {}),
          }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

export default function DepartmentCard({
  def,
  performance,
  morale,
  perfDelta,
  moraleDelta,
  compact,
}: Props) {
  const bigHit =
    Math.min(perfDelta ?? 0, moraleDelta ?? 0) <= -6 ? 'animate-shake' : '';
  return (
    <motion.div
      whileHover={{ y: -3 }}
      className={`panel rounded-2xl p-3 shadow-card ${bigHit}`}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xl">{def.icon}</span>
        <span className="font-display text-sm font-semibold">{def.name}</span>
      </div>
      <Gauge label="Performance" value={performance} delta={perfDelta} />
      {!compact && <Gauge label="Morale" value={morale} delta={moraleDelta} />}
    </motion.div>
  );
}
