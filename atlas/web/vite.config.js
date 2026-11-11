import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built into atlas/static/site and served by atlas.server at /, with client-side routes
// falling back to index.html.
export default defineConfig({
  base: '/',
  plugins: [react()],
  // Fonts stay as files: the server's CSP blocks data: fonts.
  build: { outDir: '../static/site', emptyOutDir: true, assetsInlineLimit: 0 },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
});
