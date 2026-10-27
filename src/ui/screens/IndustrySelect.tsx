import { motion } from 'framer-motion';
import { content } from '../../engine/contentLoader';
import { useGameStore } from '../../store/useGameStore';

export default function IndustrySelect() {
  const selectIndustry = useGameStore((s) => s.selectIndustry);
  const continueSaved = useGameStore((s) => s.continueSavedGame);
  const hasSave = useGameStore((s) => s.hasSave);
  const openSettings = useGameStore((s) => s.openSettings);

  return (
    <div className="mx-auto max-w-5xl py-6">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 text-center"
      >
        <h1 className="font-display text-5xl font-bold">
          <span className="gradient-text">Boardroom</span>
        </h1>
        <p className="mt-2 text-lg text-[var(--text-soft)]">
          Take the corner office. Every decision ripples through the whole company.
        </p>
        <div className="mt-4 flex items-center justify-center gap-2">
          {hasSave && (
            <button
              onClick={continueSaved}
              className="rounded-2xl px-5 py-2.5 font-display font-semibold text-black shadow-glow transition-transform hover:scale-105"
              style={{ background: 'linear-gradient(100deg, var(--primary), var(--accent))' }}
            >
              ▸ Continue Game
            </button>
          )}
          <button
            onClick={openSettings}
            className="panel rounded-2xl px-5 py-2.5 font-display font-semibold transition-colors hover:border-[var(--accent)]"
          >
            ⚙️ Settings
          </button>
        </div>
      </motion.div>

      <h2 className="mb-3 text-center font-display text-sm font-semibold uppercase tracking-widest text-[var(--text-soft)]">
        Choose your industry
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {content.industries.map((ind, i) => (
          <motion.button
            key={ind.id}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            whileHover={{ y: -6, scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => selectIndustry(ind.id)}
            className="panel group relative overflow-hidden rounded-3xl p-6 text-left shadow-card"
            style={{ borderColor: 'var(--border)' }}
          >
            <div
              className="absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-30 blur-2xl transition-opacity group-hover:opacity-60"
              style={{
                background: `radial-gradient(circle, ${ind.theme.primary}, ${ind.theme.accent})`,
              }}
            />
            <div className="relative">
              <div className="text-5xl">{ind.icon}</div>
              <h3 className="mt-3 font-display text-2xl font-bold">{ind.name}</h3>
              <p className="mt-1 text-sm text-[var(--text-soft)]">{ind.tagline}</p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {ind.departments.map((d) => (
                  <span
                    key={d.id}
                    className="rounded-lg bg-[var(--surface-2)] px-2 py-0.5 text-[11px]"
                    title={d.name}
                  >
                    {d.icon} {d.name}
                  </span>
                ))}
              </div>
            </div>
          </motion.button>
        ))}
        {content.industries.length === 0 && (
          <p className="col-span-full text-center text-[var(--text-soft)]">
            No industries found in <code>/content/industries</code>.
          </p>
        )}
      </div>

      <p className="mt-8 text-center text-xs text-[var(--text-soft)]">
        A personal project. Add more industries by dropping JSON into{' '}
        <code>/content</code> — see the README.
      </p>
    </div>
  );
}
