import { AnimatePresence, motion } from 'framer-motion';
import { useGameStore } from '../store/useGameStore';
import { getIndustry } from '../engine/contentLoader';
import IndustrySelect from './screens/IndustrySelect';
import DecisionScreen from './screens/DecisionScreen';
import QuarterReview from './screens/QuarterReview';
import CrisisScreen from './screens/CrisisScreen';
import FiredScreen from './screens/FiredScreen';
import EndScreen from './screens/EndScreen';
import SettingsScreen from './screens/SettingsScreen';
import CompanyStats from './components/CompanyStats';

export default function App() {
  const phase = useGameStore((s) => s.phase);
  const game = useGameStore((s) => s.game);
  const openSettings = useGameStore((s) => s.openSettings);
  const newGame = useGameStore((s) => s.newGame);

  const profile = game ? getIndustry(game.industryId) : undefined;
  // The persistent stats header shows during in-flight gameplay only.
  const showHeader =
    !!game && !!profile && (phase === 'decision' || phase === 'quarter-review');

  return (
    <div className="min-h-screen px-4 py-4 sm:px-6">
      {showHeader && profile && game && (
        <div className="mx-auto mb-4 max-w-6xl">
          <CompanyStats
            game={game}
            profile={profile}
            onSettings={openSettings}
            onQuit={() => {
              if (confirm('Quit to the main menu? Your game is auto-saved.')) newGame();
            }}
          />
        </div>
      )}

      <AnimatePresence mode="wait">
        <motion.div
          key={phase}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
        >
          {phase === 'industry-select' && <IndustrySelect />}
          {phase === 'decision' && <DecisionScreen />}
          {phase === 'quarter-review' && <QuarterReview />}
          {phase === 'crisis' && <CrisisScreen />}
          {phase === 'fired' && <FiredScreen />}
          {phase === 'end' && <EndScreen />}
          {phase === 'settings' && <SettingsScreen />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
