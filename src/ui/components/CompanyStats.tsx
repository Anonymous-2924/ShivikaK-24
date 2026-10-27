import { motion } from 'framer-motion';
import type { GameState, IndustryProfile } from '../../engine/types';
import { computeScore } from '../../engine/scoring';
import { performanceMultiplier } from '../../engine/metrics';
import AnimatedNumber from './AnimatedNumber';

interface Props {
  game: GameState;
  profile: IndustryProfile;
  onSettings: () => void;
  onQuit: () => void;
}

function Pill({
  label,
  children,
  warn,
}: {
  label: string;
  children: React.ReactNode;
  warn?: boolean;
}) {
  return (
    <div
      className="panel flex min-w-[96px] flex-col rounded-xl px-3 py-1.5"
      style={warn ? { borderColor: 'var(--bad)' } : undefined}
    >
      <span className="text-[10px] uppercase tracking-wide text-[var(--text-soft)]">
        {label}
      </span>
      <span className="font-display text-lg font-semibold tabular-nums">
        {children}
      </span>
    </div>
  );
}

export default function CompanyStats({ game, profile, onSettings, onQuit }: Props) {
  const score = computeScore(game);
  const lowCash = game.metrics.cash < profile.startingState.cash * 0.2;
  const projectedRevenue = Math.round(game.baseRevenue * performanceMultiplier(game));
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="mr-auto flex items-center gap-2">
        <span className="text-2xl">{profile.icon}</span>
        <div className="leading-tight">
          <div className="font-display text-sm font-semibold">{profile.name}</div>
          <div className="text-[11px] text-[var(--text-soft)]">
            Quarter {game.quarter}/{profile.quartersPerGame} · Decision{' '}
            {game.decisionInQuarter + 1}/{profile.decisionsPerQuarter}
          </div>
        </div>
      </div>

      <Pill label="Cash" warn={lowCash}>
        <AnimatedNumber
          value={game.metrics.cash}
          format={(n) => `$${Math.round(n).toLocaleString()}`}
        />
      </Pill>
      <div title="Projected revenue earned at the end of this quarter">
        <Pill label="Revenue / Q">
          <span style={{ color: 'var(--good)' }}>
            +<AnimatedNumber value={projectedRevenue} format={(n) => `$${Math.round(n).toLocaleString()}`} />
          </span>
        </Pill>
      </div>
      <Pill label="Reputation">
        <AnimatedNumber value={game.metrics.reputation} />
      </Pill>
      <Pill label="Performance">
        <AnimatedNumber value={game.metrics.performance} />
      </Pill>
      <motion.div
        key={score}
        initial={{ scale: 1 }}
        animate={{ scale: [1, 1.08, 1] }}
        transition={{ duration: 0.4 }}
      >
        <Pill label="Score">
          <span className="gradient-text">
            <AnimatedNumber value={score} />
          </span>
        </Pill>
      </motion.div>

      <div className="flex gap-1">
        <button
          onClick={onSettings}
          className="panel rounded-xl px-3 py-2 text-sm transition-colors hover:border-[var(--accent)]"
          title="Settings"
        >
          ⚙️
        </button>
        <button
          onClick={onQuit}
          className="panel rounded-xl px-3 py-2 text-sm transition-colors hover:border-[var(--bad)]"
          title="Quit to menu"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
