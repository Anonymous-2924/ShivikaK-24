import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useGameStore } from '../../store/useGameStore';
import { getIndustry } from '../../engine/contentLoader';
import { applyOption } from '../../engine/metrics';
import { allBuiltInAdvice, type AdvisorAdvice } from '../../engine/advisors';
import { liveAdvice } from '../../engine/openai';
import type { ScenarioOption } from '../../engine/types';
import OptionCard from '../components/OptionCard';
import DepartmentCard from '../components/DepartmentCard';
import AdvisorPortrait from '../components/AdvisorPortrait';
import ResolutionOverlay from '../components/ResolutionOverlay';

const TAG_COLOR: Record<string, string> = {
  opportunity: 'var(--good)',
  threat: 'var(--warn)',
  crisis: 'var(--bad)',
  routine: 'var(--accent)',
};

export default function DecisionScreen() {
  // NOTE: these can momentarily be null while AnimatePresence animates this
  // screen out (phase changes null the current scenario). Every hook below is
  // written to tolerate null; we guard the render at the end.
  const game = useGameStore((s) => s.game);
  const scenario = useGameStore((s) => s.currentScenario);
  const settings = useGameStore((s) => s.settings);
  const chooseOption = useGameStore((s) => s.chooseOption);

  const profile = game ? getIndustry(game.industryId) : undefined;

  const [hoveredDeltas, setHoveredDeltas] = useState<Record<string, { performance: number; morale: number }> | null>(null);
  const [pending, setPending] = useState<ScenarioOption | null>(null);

  // Built-in advice is instant; live advice (if enabled) fills in async.
  const builtIn = useMemo(
    () =>
      profile && scenario && game
        ? allBuiltInAdvice(profile.advisors, scenario, game)
        : [],
    [profile, scenario, game],
  );
  const [advice, setAdvice] = useState<AdvisorAdvice[]>(builtIn);
  const [liveLoading, setLiveLoading] = useState(false);

  const scenarioId = scenario?.id;
  useEffect(() => {
    setAdvice(builtIn);
    if (!profile || !scenario || !game) return;
    if (settings.adviceMode !== 'live' || !settings.openaiKey) return;
    let cancelled = false;
    setLiveLoading(true);
    (async () => {
      const results = await Promise.all(
        profile.advisors.map((a) =>
          liveAdvice(a, scenario, game, settings.openaiKey, settings.openaiModel),
        ),
      );
      if (cancelled) return;
      setAdvice((prev) => prev.map((base, i) => results[i] ?? base));
      setLiveLoading(false);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, settings.adviceMode, settings.openaiKey, settings.openaiModel]);

  // Preview the pending option's resulting state (pure, not committed yet).
  const preview = useMemo(() => {
    if (!pending || !game) return null;
    return applyOption(game, pending);
  }, [pending, game]);

  if (!game || !scenario || !profile) return null;

  const tagColor = TAG_COLOR[scenario.tagType] ?? 'var(--accent)';

  return (
    <div className="mx-auto max-w-6xl">
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        {/* Scenario + options */}
        <motion.div
          key={scenario.id}
          initial={{ opacity: 0, x: -24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-4"
        >
          <div className="panel rounded-3xl p-5 shadow-card">
            <span
              className="inline-block rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-wide"
              style={{ background: tagColor, color: '#0b0b18' }}
            >
              {scenario.tag}
            </span>
            <h2 className="mt-3 font-display text-2xl font-bold leading-tight">
              {scenario.title}
            </h2>
            <p className="mt-2 leading-relaxed text-[var(--text-soft)]">
              {scenario.situation}
            </p>
          </div>

          <div className="space-y-3">
            {scenario.options.map((opt) => {
              const recommendedBy = advice.filter(
                (a) => a.recommendedOptionId === opt.id,
              ).length;
              return (
                <OptionCard
                  key={opt.id}
                  option={opt}
                  departments={profile.departments}
                  recommended={recommendedBy > 0}
                  onHover={(h) =>
                    setHoveredDeltas(
                      h
                        ? Object.fromEntries(
                            profile.departments.map((d) => [
                              d.id,
                              opt.effects.departments[d.id] ?? {
                                performance: 0,
                                morale: 0,
                              },
                            ]),
                          )
                        : null,
                    )
                  }
                  onChoose={() => setPending(opt)}
                />
              );
            })}
          </div>
        </motion.div>

        {/* Advisor panel */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wide text-[var(--text-soft)]">
              The Boardroom
            </h3>
            <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px]">
              {settings.adviceMode === 'live' && settings.openaiKey
                ? liveLoading
                  ? '🤖 AI thinking…'
                  : '🤖 AI advisors'
                : '💬 Built-in advisors'}
            </span>
          </div>
          {profile.advisors.map((adv) => {
            const a = advice.find((x) => x.department === adv.department)!;
            const rec = scenario.options.find((o) => o.id === a.recommendedOptionId);
            return (
              <motion.div
                key={adv.department}
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                className="panel flex gap-3 rounded-2xl p-3 shadow-card"
              >
                <div className="shrink-0">
                  <AdvisorPortrait
                    expression={a.expression}
                    color={profile.theme.primary}
                    reacting={!!hoveredDeltas}
                  />
                </div>
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="font-display text-sm font-semibold">
                      {a.advisorName}
                    </span>
                    <span className="text-[10px] text-[var(--text-soft)]">
                      {adv.department}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs leading-snug text-[var(--text-soft)]">
                    {a.text}
                  </p>
                  {rec && (
                    <p className="mt-1 text-[11px]">
                      <span className="text-[var(--text-soft)]">Recommends: </span>
                      <span className="font-semibold text-[var(--accent)]">
                        {rec.label}
                      </span>
                    </p>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Live department dashboard */}
      <div className="mt-5">
        <h3 className="mb-2 font-display text-sm font-semibold uppercase tracking-wide text-[var(--text-soft)]">
          Company Overview
        </h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
          {profile.departments.map((d) => {
            const state = game.departments.find((s) => s.id === d.id)!;
            const hd = hoveredDeltas?.[d.id];
            return (
              <DepartmentCard
                key={d.id}
                def={d}
                performance={state.performance}
                morale={state.morale}
                perfDelta={hd?.performance}
                moraleDelta={hd?.morale}
              />
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {pending && preview && (
          <ResolutionOverlay
            profile={profile}
            optionLabel={pending.label}
            outcomeText={pending.outcomeText}
            cashChange={pending.cashChange}
            revenueDelta={pending.revenueDelta}
            recurring={pending.recurring}
            companyDelta={preview.companyDelta}
            resultDepartments={preview.next.departments}
            deptDeltas={preview.deptDeltas}
            onContinue={() => {
              const opt = pending;
              setPending(null);
              setHoveredDeltas(null);
              chooseOption(opt);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
