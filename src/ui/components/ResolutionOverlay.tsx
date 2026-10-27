import { motion } from 'framer-motion';
import type {
  DepartmentState,
  DeptEffect,
  IndustryProfile,
  RecurringEffect,
} from '../../engine/types';
import DepartmentCard from './DepartmentCard';

interface Props {
  profile: IndustryProfile;
  optionLabel: string;
  outcomeText: string;
  cashChange: number;
  revenueDelta?: number;
  recurring?: RecurringEffect[];
  companyDelta: { reputation: number; performance: number };
  resultDepartments: DepartmentState[];
  deptDeltas: Record<string, DeptEffect>;
  onContinue: () => void;
}

function CompanyDelta({ label, value, money }: { label: string; value: number; money?: boolean }) {
  if (value === 0 && !money) return null;
  if (money && value === 0) return null;
  const pos = value > 0;
  const text = money
    ? `${pos ? '+' : '-'}$${Math.abs(value).toLocaleString()}`
    : `${pos ? '+' : ''}${value}`;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className="panel rounded-xl px-4 py-2 text-center"
    >
      <div className="text-[10px] uppercase tracking-wide text-[var(--text-soft)]">
        {label}
      </div>
      <div
        className="font-display text-xl font-bold"
        style={{ color: pos ? 'var(--good)' : 'var(--bad)' }}
      >
        {text}
      </div>
    </motion.div>
  );
}

export default function ResolutionOverlay({
  profile,
  optionLabel,
  outcomeText,
  cashChange,
  revenueDelta,
  recurring,
  companyDelta,
  resultDepartments,
  deptDeltas,
  onContinue,
}: Props) {
  // Most-affected department (largest absolute combined swing).
  let topDept = profile.departments[0];
  let topMag = -1;
  for (const d of profile.departments) {
    const e = deptDeltas[d.id];
    if (!e) continue;
    const mag = Math.abs(e.performance) + Math.abs(e.morale);
    if (mag > topMag) {
      topMag = mag;
      topDept = d;
    }
  }
  const topEffect = deptDeltas[topDept.id] ?? { performance: 0, morale: 0 };
  const topPositive = topEffect.performance + topEffect.morale >= 0;

  const bigWin =
    companyDelta.reputation + companyDelta.performance >= 10 || cashChange >= 25000;
  const bigLoss =
    companyDelta.reputation + companyDelta.performance <= -10 || cashChange <= -25000;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-40 flex items-center justify-center p-4"
      style={{ background: 'rgba(5,4,15,0.72)', backdropFilter: 'blur(6px)' }}
    >
      {bigLoss && (
        <motion.div
          className="pointer-events-none absolute inset-0"
          style={{ background: 'var(--bad)' }}
          initial={{ opacity: 0.5 }}
          animate={{ opacity: 0 }}
          transition={{ duration: 0.6 }}
        />
      )}
      {bigWin && <Confetti />}

      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        className={`panel w-full max-w-3xl rounded-3xl p-6 shadow-card ${
          bigLoss ? 'animate-shake' : ''
        }`}
      >
        <div className="mb-1 text-[11px] uppercase tracking-widest text-[var(--accent)]">
          Decision made
        </div>
        <h3 className="font-display text-2xl font-bold">{optionLabel}</h3>
        <p className="mt-2 text-[var(--text-soft)]">{outcomeText}</p>

        <div className="mt-4 flex flex-wrap justify-center gap-3">
          <CompanyDelta label="Cash" value={cashChange} money />
          <CompanyDelta label="Reputation" value={companyDelta.reputation} />
          <CompanyDelta label="Performance" value={companyDelta.performance} />
        </div>

        {(!!revenueDelta || (recurring && recurring.length > 0)) && (
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2 text-xs">
            {!!revenueDelta && (
              <span
                className="rounded-lg bg-[var(--surface-2)] px-3 py-1 font-semibold"
                style={{ color: revenueDelta > 0 ? 'var(--good)' : 'var(--bad)' }}
              >
                Quarterly revenue {revenueDelta > 0 ? '+' : '-'}$
                {Math.abs(revenueDelta).toLocaleString()} (permanent)
              </span>
            )}
            {(recurring ?? []).map((r, i) => {
              const perQ = (r.cashPerQuarter ?? 0) + (r.revenuePerQuarter ?? 0);
              return (
                <span
                  key={i}
                  className="rounded-lg bg-[var(--surface-2)] px-3 py-1"
                  style={{ color: perQ < 0 ? 'var(--bad)' : 'var(--good)' }}
                >
                  {r.label}: {perQ > 0 ? '+' : '-'}${Math.abs(perQ).toLocaleString()}/qtr for{' '}
                  {r.quarters}q
                </span>
              );
            })}
          </div>
        )}

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mt-4 rounded-xl bg-[var(--surface-2)] px-4 py-2 text-center text-sm"
        >
          <span className="text-xl">{topDept.icon}</span>{' '}
          <strong>{topDept.name}</strong>{' '}
          {topPositive ? 'is energized' : 'took the biggest hit'} this round.
        </motion.div>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
          {profile.departments.map((d) => {
            const state = resultDepartments.find((s) => s.id === d.id)!;
            const delta = deptDeltas[d.id] ?? { performance: 0, morale: 0 };
            return (
              <DepartmentCard
                key={d.id}
                def={d}
                performance={state.performance}
                morale={state.morale}
                perfDelta={delta.performance}
                moraleDelta={delta.morale}
              />
            );
          })}
        </div>

        <button
          onClick={onContinue}
          className="mt-6 w-full rounded-2xl py-3 font-display text-lg font-semibold text-black shadow-glow transition-transform hover:scale-[1.02]"
          style={{ background: 'linear-gradient(100deg, var(--primary), var(--accent))' }}
        >
          Continue →
        </button>
      </motion.div>
    </motion.div>
  );
}

/** Lightweight confetti burst for big wins. */
function Confetti() {
  const colors = ['#7C3AED', '#06B6D4', '#F59E0B', '#22c55e', '#ec4899'];
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {Array.from({ length: 40 }).map((_, i) => (
        <motion.span
          key={i}
          className="absolute h-2 w-2 rounded-sm"
          style={{
            left: `${Math.random() * 100}%`,
            top: '-5%',
            background: colors[i % colors.length],
          }}
          initial={{ y: -20, opacity: 1, rotate: 0 }}
          animate={{ y: '110vh', opacity: [1, 1, 0], rotate: 360 }}
          transition={{ duration: 1.6 + Math.random(), delay: Math.random() * 0.3, ease: 'easeIn' }}
        />
      ))}
    </div>
  );
}
