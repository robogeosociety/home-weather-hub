import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5189,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8770', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8770', ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
