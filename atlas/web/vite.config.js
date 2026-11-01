import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built into atlas/static/tree and served by atlas.server at /tree.
export default defineConfig({
  base: '/tree/',
  plugins: [react()],
  // Fonts stay as files: the server's CSP blocks data: fonts.
  build: { outDir: '../static/tree', emptyOutDir: true, assetsInlineLimit: 0 },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
});
