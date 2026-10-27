import { motion } from 'framer-motion';
import { useGameStore } from '../../store/useGameStore';
import { getIndustry } from '../../engine/contentLoader';
import { computeScore, letterGrade } from '../../engine/scoring';
import { avgMorale } from '../../engine/metrics';
import type { GameState } from '../../engine/types';

/** A savage-but-playful one-liner, chosen from the company's worst trait. */
function roast(game: GameState): string {
  const morale = avgMorale(game.departments);
  const lines: { cond: boolean; text: string }[] = [
    {
      cond: game.metrics.cash < 0,
      text: "You turned a bank account into a crater. Impressive, in the way a sinkhole is impressive.",
    },
    {
      cond: game.flags.includes('downplayed_safety'),
      text: "You buried the bad news so deep it came back with a lawyer. Bold strategy. Didn't work.",
    },
    {
      cond: game.flags.includes('fire_sold'),
      text: "You sold the furniture to pay the rent, then wondered why there was nowhere to sit.",
    },
    {
      cond: morale < 35,
      text: "The staff didn't quit — they simply stopped making eye contact. That's its own kind of resignation.",
    },
    {
      cond: game.metrics.reputation < 35,
      text: "Our brand now polls somewhere between 'parking ticket' and 'dial-up tone.'",
    },
    {
      cond: game.metrics.performance < 35,
      text: "The company ran like a clock — a broken one, twice a day, on a good day.",
    },
    {
      cond: true,
      text: "You had one job. Technically several jobs. You have, as of now, none of them.",
    },
  ];
  return lines.find((l) => l.cond)!.text;
}

export default function FiredScreen() {
  const game = useGameStore((s) => s.game);
  const reason = useGameStore((s) => s.firedReason);
  const newGame = useGameStore((s) => s.newGame);
  if (!game) return null;
  const profile = getIndustry(game.industryId)!;
  const score = computeScore(game);
  const grade = letterGrade(score);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-auto p-4"
      style={{
        background:
          'radial-gradient(1200px 700px at 50% -10%, #7f1d1d, #2a0505 60%, #120203)',
      }}
    >
      <motion.div
        initial={{ scale: 0.7, rotate: -4, y: -40 }}
        animate={{ scale: 1, rotate: 0, y: 0 }}
        transition={{ type: 'spring', stiffness: 160, damping: 12 }}
        className="relative w-full max-w-2xl text-center"
      >
        {/* Gavel slam */}
        <motion.div
          initial={{ rotate: -60, y: -30, opacity: 0 }}
          animate={{ rotate: [-60, 10, -8, 0], y: [-30, 0, 0, 0], opacity: 1 }}
          transition={{ duration: 0.8, times: [0, 0.5, 0.75, 1] }}
          onAnimationComplete={() => {}}
          className="mx-auto mb-2 text-7xl"
        >
          🔨
        </motion.div>

        <motion.h1
          initial={{ scale: 1 }}
          animate={{ scale: [1, 1.06, 1] }}
          transition={{ delay: 0.4, duration: 0.5 }}
          className="font-display text-6xl font-black tracking-tight text-white drop-shadow-[0_4px_0_rgba(0,0,0,0.4)] sm:text-7xl"
        >
          YOU'RE FIRED
        </motion.h1>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="animate-shake"
        >
          <div className="mx-auto mt-4 max-w-xl rounded-3xl border border-white/20 bg-black/40 p-5 backdrop-blur">
            <div className="mb-1 text-4xl">🧑‍⚖️</div>
            <div className="text-[11px] uppercase tracking-widest text-[#ffb3b3]">
              The Board Chairman clears his throat
            </div>
            <p className="mt-2 text-lg font-semibold text-white">“{roast(game)}”</p>
            <p className="mt-3 text-sm text-[#e9c7c7]">{reason}</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.9 }}
          className="mt-5 flex items-center justify-center gap-3"
        >
          <div className="rounded-2xl bg-black/40 px-5 py-3">
            <div className="text-[10px] uppercase tracking-wide text-[#ffb3b3]">
              Final score
            </div>
            <div className="font-display text-3xl font-bold text-white">{score}</div>
          </div>
          <div className="rounded-2xl bg-black/40 px-5 py-3">
            <div className="text-[10px] uppercase tracking-wide text-[#ffb3b3]">Grade</div>
            <div className="font-display text-3xl font-bold text-[var(--warn)]">{grade}</div>
          </div>
          <div className="rounded-2xl bg-black/40 px-5 py-3">
            <div className="text-[10px] uppercase tracking-wide text-[#ffb3b3]">
              Survived
            </div>
            <div className="font-display text-3xl font-bold text-white">
              {game.quarter}Q
            </div>
          </div>
        </motion.div>

        <p className="mt-4 text-xs text-[#e9c7c7]">
          You ran {profile.name} for {game.quarter} quarter(s) before the board
          intervened.
        </p>

        <motion.button
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.1 }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.97 }}
          onClick={newGame}
          className="mt-6 rounded-2xl bg-white px-8 py-3 font-display text-lg font-bold text-[#7f1d1d] shadow-xl"
        >
          Try Again ↻
        </motion.button>
      </motion.div>
    </motion.div>
  );
}
