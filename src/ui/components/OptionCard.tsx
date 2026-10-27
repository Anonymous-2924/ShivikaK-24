import { motion } from 'framer-motion';
import type { DepartmentDef, ScenarioOption } from '../../engine/types';
import { cashDir, DIR_ARROW, dirColor, toDir } from './hints';

interface Props {
  option: ScenarioOption;
  departments: DepartmentDef[];
  recommended?: boolean;
  onHover: (hovering: boolean) => void;
  onChoose: () => void;
}

const RISK_COLOR: Record<string, string> = {
  low: 'var(--good)',
  medium: 'var(--warn)',
  high: 'var(--bad)',
};

/** The dominant direction for a department (max-magnitude of perf/morale). */
function deptDir(option: ScenarioOption, deptId: string) {
  const e = option.effects.departments[deptId];
  if (!e) return toDir(0);
  const dominant =
    Math.abs(e.performance) >= Math.abs(e.morale) ? e.performance : e.morale;
  return toDir(dominant);
}

export default function OptionCard({
  option,
  departments,
  recommended,
  onHover,
  onChoose,
}: Props) {
  const cd = cashDir(option.cashChange);
  const repDir = toDir(option.effects.company.reputation);
  const perfDir = toDir(option.effects.company.performance);

  return (
    <motion.button
      type="button"
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onFocus={() => onHover(true)}
      onBlur={() => onHover(false)}
      onClick={onChoose}
      whileHover={{ y: -4, rotateX: 2, rotateY: -2 }}
      whileTap={{ scale: 0.98 }}
      className="panel group relative w-full rounded-2xl p-4 text-left shadow-card transition-colors hover:border-[var(--accent)]"
      style={{ transformStyle: 'preserve-3d' }}
    >
      {recommended && (
        <span className="absolute -top-2 right-3 rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-bold text-black shadow-glow">
          ADVISOR PICK
        </span>
      )}
      <div className="flex items-center justify-between gap-2">
        <span className="font-display text-base font-semibold">{option.label}</span>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase"
          style={{ background: RISK_COLOR[option.risk], color: '#0b0b18' }}
        >
          {option.risk} risk
        </span>
      </div>
      <p className="mt-1 text-sm text-[var(--text-soft)]">{option.description}</p>

      {/* Impact preview — directional only, revealed on hover/focus. */}
      <div className="mt-3 max-h-0 overflow-hidden opacity-0 transition-all duration-300 group-hover:max-h-40 group-hover:opacity-100 group-focus:max-h-40 group-focus:opacity-100">
        <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
          <Hint label="Cash" dir={cd} />
          <Hint label="Reputation" dir={repDir} />
          <Hint label="Performance" dir={perfDir} />
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          {departments.map((d) => {
            const dir = deptDir(option, d.id);
            return (
              <span
                key={d.id}
                className="flex items-center gap-1 rounded-lg bg-[var(--surface-2)] px-1.5 py-0.5"
                title={`${d.name} likely ${dir}`}
              >
                <span>{d.icon}</span>
                <span style={{ color: dirColor(dir) }}>{DIR_ARROW[dir]}</span>
              </span>
            );
          })}
        </div>
        <p className="mt-2 text-[10px] italic text-[var(--text-soft)]">
          Directions are estimates — exact impact revealed after you decide.
        </p>
      </div>
    </motion.button>
  );
}

function Hint({ label, dir }: { label: string; dir: ReturnType<typeof toDir> }) {
  return (
    <span className="flex items-center gap-1 rounded-lg bg-[var(--surface-2)] px-1.5 py-0.5">
      <span className="text-[var(--text-soft)]">{label}</span>
      <span style={{ color: dirColor(dir) }}>{DIR_ARROW[dir]}</span>
    </span>
  );
}
