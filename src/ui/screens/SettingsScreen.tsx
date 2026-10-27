import { useState } from 'react';
import { motion } from 'framer-motion';
import { useGameStore } from '../../store/useGameStore';
import { validateKey } from '../../engine/openai';

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  'not-set': { text: 'Not set', color: 'var(--text-soft)' },
  valid: { text: '✓ Valid', color: 'var(--good)' },
  invalid: { text: '✗ Invalid', color: 'var(--bad)' },
  unknown: { text: '? Unverified', color: 'var(--warn)' },
};

export default function SettingsScreen() {
  const settings = useGameStore((s) => s.settings);
  const setTheme = useGameStore((s) => s.setTheme);
  const setAdviceMode = useGameStore((s) => s.setAdviceMode);
  const setOpenAiKey = useGameStore((s) => s.setOpenAiKey);
  const setOpenAiModel = useGameStore((s) => s.setOpenAiModel);
  const setKeyStatus = useGameStore((s) => s.setKeyStatus);
  const back = useGameStore((s) => s.backFromSettings);

  const [keyInput, setKeyInput] = useState(settings.openaiKey);
  const [testing, setTesting] = useState(false);

  const activeMode =
    settings.adviceMode === 'live' && settings.openaiKey && settings.keyStatus === 'valid'
      ? 'Live AI advisors'
      : 'Built-in advisors';

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto max-w-2xl py-6"
    >
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-3xl font-bold">
          <span className="gradient-text">Settings</span>
        </h1>
        <button
          onClick={back}
          className="panel rounded-xl px-4 py-2 text-sm transition-colors hover:border-[var(--accent)]"
        >
          ← Back
        </button>
      </div>

      {/* Theme */}
      <section className="panel mb-4 rounded-2xl p-5">
        <h2 className="font-display text-lg font-semibold">Appearance</h2>
        <p className="mb-3 text-sm text-[var(--text-soft)]">
          Both themes are colorful — pick your mood.
        </p>
        <div className="flex gap-2">
          {(['dark', 'light'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTheme(t)}
              className={`rounded-xl px-4 py-2 font-semibold capitalize transition-all ${
                settings.theme === t
                  ? 'text-black shadow-glow'
                  : 'panel text-[var(--text-soft)]'
              }`}
              style={
                settings.theme === t
                  ? { background: 'linear-gradient(100deg, var(--primary), var(--accent))' }
                  : undefined
              }
            >
              {t === 'dark' ? '🌙' : '☀️'} {t}
            </button>
          ))}
        </div>
      </section>

      {/* Advice mode */}
      <section className="panel mb-4 rounded-2xl p-5">
        <h2 className="font-display text-lg font-semibold">Advisor advice</h2>
        <p className="mb-1 text-sm text-[var(--text-soft)]">
          Active mode: <strong style={{ color: 'var(--accent)' }}>{activeMode}</strong>
        </p>
        <p className="mb-3 text-xs text-[var(--text-soft)]">
          The game is fully playable in Built-in mode with no key. Live AI is optional.
        </p>
        <div className="flex gap-2">
          {(['builtin', 'live'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setAdviceMode(m)}
              className={`rounded-xl px-4 py-2 font-semibold transition-all ${
                settings.adviceMode === m
                  ? 'text-black shadow-glow'
                  : 'panel text-[var(--text-soft)]'
              }`}
              style={
                settings.adviceMode === m
                  ? { background: 'linear-gradient(100deg, var(--primary), var(--accent))' }
                  : undefined
              }
            >
              {m === 'builtin' ? '💬 Built-in (offline)' : '🤖 Live AI (OpenAI)'}
            </button>
          ))}
        </div>
      </section>

      {/* OpenAI key */}
      <section className="panel mb-4 rounded-2xl p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">OpenAI API key</h2>
          <span
            className="text-sm font-semibold"
            style={{ color: STATUS_LABEL[settings.keyStatus].color }}
          >
            {STATUS_LABEL[settings.keyStatus].text}
          </span>
        </div>
        <p className="mb-3 mt-1 text-xs text-[var(--text-soft)]">
          Stored locally in your browser only (never committed, never sent anywhere
          except OpenAI). Using the API may incur costs on your OpenAI account. The
          key is <strong>optional</strong>.
        </p>
        <input
          type="password"
          value={keyInput}
          onChange={(e) => setKeyInput(e.target.value)}
          placeholder="sk-..."
          className="w-full rounded-xl bg-[var(--surface-2)] px-3 py-2 font-mono text-sm outline-none ring-[var(--accent)] focus:ring-2"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={() => {
              setOpenAiKey(keyInput.trim());
            }}
            className="rounded-xl px-4 py-2 text-sm font-semibold text-black"
            style={{ background: 'linear-gradient(100deg, var(--primary), var(--accent))' }}
          >
            Save key
          </button>
          <button
            disabled={testing || !keyInput.trim()}
            onClick={async () => {
              setTesting(true);
              setOpenAiKey(keyInput.trim());
              const status = await validateKey(keyInput.trim());
              setKeyStatus(status);
              setTesting(false);
            }}
            className="panel rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:border-[var(--accent)] disabled:opacity-40"
          >
            {testing ? 'Testing…' : 'Test connection'}
          </button>
          <button
            onClick={() => {
              setKeyInput('');
              setOpenAiKey('');
              setKeyStatus('not-set');
            }}
            className="panel rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:border-[var(--bad)]"
          >
            Clear
          </button>
        </div>

        <label className="mt-4 block text-sm text-[var(--text-soft)]">
          Model
          <input
            type="text"
            value={settings.openaiModel}
            onChange={(e) => setOpenAiModel(e.target.value)}
            className="mt-1 w-full rounded-xl bg-[var(--surface-2)] px-3 py-2 font-mono text-sm outline-none ring-[var(--accent)] focus:ring-2"
          />
          <span className="mt-1 block text-xs">
            Defaults to a cheap, fast model (<code>gpt-4o-mini</code>). I'm not
            certain which model names are current for your account — verify in your
            OpenAI dashboard.
          </span>
        </label>
      </section>
    </motion.div>
  );
}
