import { motion } from 'framer-motion';
import { useGameStore } from '../../store/useGameStore';
import { getIndustry } from '../../engine/contentLoader';

function Delta({ label, value, money }: { label: string; value: number; money?: boolean }) {
  const pos = value > 0;
  const neutral = value === 0;
  const text = money
    ? `${pos ? '+' : value < 0 ? '-' : ''}$${Math.abs(value).toLocaleString()}`
    : `${pos ? '+' : ''}${value}`;
  return (
    <div className="panel flex flex-col items-center rounded-2xl px-4 py-3">
      <span className="text-[10px] uppercase tracking-wide text-[var(--text-soft)]">
        {label}
      </span>
      <span
        className="font-display text-2xl font-bold"
        style={{ color: neutral ? 'var(--text-soft)' : pos ? 'var(--good)' : 'var(--bad)' }}
      >
        {neutral ? '—' : text}
      </span>
    </div>
  );
}

export default function QuarterReview() {
  const game = useGameStore((s) => s.game);
  const advance = useGameStore((s) => s.advanceAfterQuarterReview);
  if (!game) return null;
  const profile = getIndustry(game.industryId)!;

  const cashDelta = game.metrics.cash - game.quarterStartMetrics.cash;
  const repDelta = game.metrics.reputation - game.quarterStartMetrics.reputation;
  const perfDelta = game.metrics.performance - game.quarterStartMetrics.performance;

  const quarterLogs = game.history.filter((h) => h.quarter === game.quarter);
  const isLast = game.quarter >= profile.quartersPerGame;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      className="mx-auto max-w-3xl py-8"
    >
      <div className="text-center">
        <div className="text-[11px] uppercase tracking-widest text-[var(--accent)]">
          Quarter {game.quarter} review
        </div>
        <h2 className="mt-1 font-display text-3xl font-bold">The books are closed</h2>
      </div>

      <div className="mt-6 grid grid-cols-3 gap-3">
        <Delta label="Cash" value={cashDelta} money />
        <Delta label="Reputation" value={repDelta} />
        <Delta label="Performance" value={perfDelta} />
      </div>

      <div className="mt-6">
        <h3 className="mb-2 font-display text-sm font-semibold uppercase tracking-wide text-[var(--text-soft)]">
          Department standing
        </h3>
        <div className="space-y-2">
          {profile.departments.map((d, i) => {
            const now = game.departments.find((s) => s.id === d.id)!;
            const start = game.quarterStartDepartments.find((s) => s.id === d.id)!;
            const dp = now.performance - start.performance;
            const dm = now.morale - start.morale;
            return (
              <motion.div
                key={d.id}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.08 }}
                className="panel flex items-center gap-3 rounded-xl px-3 py-2"
              >
                <span className="text-xl">{d.icon}</span>
                <span className="w-28 font-display text-sm font-semibold">{d.name}</span>
                <span className="flex-1 text-xs text-[var(--text-soft)]">
                  Perf {now.performance}{' '}
                  <em style={{ color: dp >= 0 ? 'var(--good)' : 'var(--bad)' }}>
                    ({dp >= 0 ? '+' : ''}{dp})
                  </em>{' '}
                  · Morale {now.morale}{' '}
                  <em style={{ color: dm >= 0 ? 'var(--good)' : 'var(--bad)' }}>
                    ({dm >= 0 ? '+' : ''}{dm})
                  </em>
                </span>
              </motion.div>
            );
          })}
        </div>
      </div>

      {quarterLogs.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 font-display text-sm font-semibold uppercase tracking-wide text-[var(--text-soft)]">
            Decisions this quarter
          </h3>
          <ul className="space-y-1.5">
            {quarterLogs.map((l, i) => (
              <li key={i} className="panel rounded-xl px-3 py-2 text-sm">
                <strong>{l.scenarioTitle}:</strong>{' '}
                <span className="text-[var(--accent)]">{l.optionLabel}</span>
                <span className="block text-xs italic text-[var(--text-soft)]">
                  {l.outcomeText}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={advance}
        className="mt-8 w-full rounded-2xl py-3 font-display text-lg font-semibold text-black shadow-glow transition-transform hover:scale-[1.02]"
        style={{ background: 'linear-gradient(100deg, var(--primary), var(--accent))' }}
      >
        {isLast ? 'See final results →' : `Begin Quarter ${game.quarter + 1} →`}
      </button>
    </motion.div>
  );
}
