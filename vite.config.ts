import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Boardroom web app config.
// `content/` lives at the project root (outside src) and is loaded at runtime
// via import.meta.glob (see src/engine/contentLoader.ts). Vite serves project
// root by default, so the glob resolves without extra config.
export default defineConfig({
  plugins: [react()],
  // Tauri expects a fixed dev port and relative asset paths in the build.
  base: './',
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: false,
  },
  build: {
    outDir: 'dist',
    target: 'es2021',
  },
});
