import { motion } from 'framer-motion';
import { useGameStore } from '../../store/useGameStore';
import type { Scenario } from '../../engine/types';

export default function CrisisScreen() {
  const game = useGameStore((s) => s.game);
  const lifelines = useGameStore((s) => s.pendingLifelines);
  const reason = useGameStore((s) => s.crisisReason);
  const resolve = useGameStore((s) => s.resolveLifeline);
  if (!game) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-auto p-4"
      style={{
        background:
          'radial-gradient(1000px 600px at 50% 0%, rgba(239,68,68,0.35), rgba(10,4,10,0.96))',
      }}
    >
      {/* pulsing warning glow */}
      <div className="pointer-events-none absolute inset-0 animate-pulseGlow" style={{ boxShadow: 'inset 0 0 160px 40px rgba(239,68,68,0.5)' }} />

      <motion.div
        initial={{ scale: 0.92, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        className="relative w-full max-w-4xl"
      >
        <motion.div
          animate={{ scale: [1, 1.04, 1] }}
          transition={{ repeat: Infinity, duration: 1.4 }}
          className="mx-auto mb-3 w-fit rounded-full border-2 border-[var(--bad)] px-6 py-1.5 font-display text-sm font-bold uppercase tracking-[0.3em] text-[var(--bad)]"
        >
          ⚠ Insolvency ⚠
        </motion.div>

        <h2 className="text-center font-display text-4xl font-black text-white drop-shadow">
          The company is out of cash
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-[#ffd9d9]">
          {reason} Current balance:{' '}
          <strong>${game.metrics.cash.toLocaleString()}</strong>. Pick one lifeline —
          each has a real, lasting cost.
        </p>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {lifelines.map((ll: Scenario, i) => {
            const opt = ll.options[0];
            return (
              <motion.button
                key={ll.id}
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                whileHover={{ y: -6, scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => resolve(ll, opt)}
                className="flex flex-col rounded-3xl border border-[var(--bad)]/60 bg-[#1a0c12]/90 p-5 text-left shadow-card backdrop-blur"
              >
                <h3 className="font-display text-xl font-bold text-white">{ll.title}</h3>
                <p className="mt-2 text-sm text-[#e9c7c7]">{ll.situation}</p>
                <div className="mt-3 rounded-xl bg-[#2a1118] px-3 py-2">
                  <div className="font-display text-2xl font-bold text-[var(--good)]">
                    +${opt.cashChange.toLocaleString()}
                  </div>
                  <div className="mt-1 text-xs text-[#ffb3b3]">{opt.description}</div>
                </div>
                <div className="mt-auto pt-3 text-xs text-[#e9c7c7]">
                  {opt.effects.company.reputation !== 0 && (
                    <span className="mr-2">
                      Reputation {opt.effects.company.reputation > 0 ? '+' : ''}
                      {opt.effects.company.reputation}
                    </span>
                  )}
                  {opt.scoreMultiplierDelta && (
                    <span className="mr-2">
                      Final score ×{(1 + opt.scoreMultiplierDelta).toFixed(2)}
                    </span>
                  )}
                </div>
                <span className="mt-3 rounded-xl bg-[var(--bad)] py-2 text-center font-display font-semibold text-white">
                  Take this lifeline
                </span>
              </motion.button>
            );
          })}
        </div>

        <p className="mt-6 text-center text-xs text-[#ffb3b3]">
          This is your one shot at redemption. Fail again and the board shows you the door.
        </p>
      </motion.div>
    </motion.div>
  );
}
