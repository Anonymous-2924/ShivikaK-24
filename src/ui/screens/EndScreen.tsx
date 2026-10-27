import { motion } from 'framer-motion';
import { useGameStore } from '../../store/useGameStore';
import { getIndustry } from '../../engine/contentLoader';
import { computeScore, letterGrade, gradeBlurb } from '../../engine/scoring';
import { avgMorale } from '../../engine/metrics';

export default function EndScreen() {
  const game = useGameStore((s) => s.game);
  const newGame = useGameStore((s) => s.newGame);
  if (!game) return null;
  const profile = getIndustry(game.industryId)!;
  const score = computeScore(game);
  const grade = letterGrade(score);
  const great = score >= 70;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto max-w-2xl py-10 text-center"
    >
      {great && <Confetti />}
      <div className="text-[11px] uppercase tracking-widest text-[var(--accent)]">
        Tenure complete · {profile.name}
      </div>
      <h1 className="mt-2 font-display text-5xl font-black">
        <span className="gradient-text">Your Legacy</span>
      </h1>

      <motion.div
        initial={{ scale: 0.6, rotate: -8 }}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ type: 'spring', stiffness: 160, damping: 11 }}
        className="mx-auto mt-6 flex h-36 w-36 items-center justify-center rounded-full shadow-glow"
        style={{ background: 'linear-gradient(135deg, var(--primary), var(--accent))' }}
      >
        <span className="font-display text-7xl font-black text-white drop-shadow">
          {grade}
        </span>
      </motion.div>

      <div className="mt-5 font-display text-3xl font-bold">
        Score: <span className="gradient-text">{score}</span>
      </div>
      <p className="mx-auto mt-2 max-w-md text-[var(--text-soft)]">
        {gradeBlurb(grade, false)}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Cash" value={`$${game.metrics.cash.toLocaleString()}`} />
        <Stat label="Reputation" value={game.metrics.reputation} />
        <Stat label="Performance" value={game.metrics.performance} />
        <Stat label="Avg Morale" value={Math.round(avgMorale(game.departments))} />
      </div>

      {game.flags.includes('used_second_chance') && (
        <p className="mt-4 text-sm italic text-[var(--warn)]">
          ⚑ You clawed back from the brink of insolvency — and lived to tell the tale.
        </p>
      )}

      <button
        onClick={newGame}
        className="mt-8 rounded-2xl px-8 py-3 font-display text-lg font-semibold text-black shadow-glow transition-transform hover:scale-105"
        style={{ background: 'linear-gradient(100deg, var(--primary), var(--accent))' }}
      >
        Play Again ↻
      </button>
    </motion.div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="panel rounded-2xl px-3 py-3">
      <div className="text-[10px] uppercase tracking-wide text-[var(--text-soft)]">
        {label}
      </div>
      <div className="font-display text-xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function Confetti() {
  const colors = ['#7C3AED', '#06B6D4', '#F59E0B', '#22c55e', '#ec4899'];
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden">
      {Array.from({ length: 60 }).map((_, i) => (
        <motion.span
          key={i}
          className="absolute h-2.5 w-2.5 rounded-sm"
          style={{ left: `${Math.random() * 100}%`, top: '-5%', background: colors[i % colors.length] }}
          initial={{ y: -20, opacity: 1, rotate: 0 }}
          animate={{ y: '110vh', opacity: [1, 1, 0], rotate: 540 }}
          transition={{ duration: 2 + Math.random() * 1.5, delay: Math.random() * 0.6, ease: 'easeIn' }}
        />
      ))}
    </div>
  );
}
