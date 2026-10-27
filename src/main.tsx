import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './ui/App';
import './styles.css';
import { useGameStore } from './store/useGameStore';

// Apply the persisted theme (light/dark) before first paint-ish.
const initialTheme = useGameStore.getState().settings.theme;
document.documentElement.classList.toggle('dark', initialTheme === 'dark');

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
