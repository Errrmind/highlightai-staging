import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxyTarget =
    env.VITE_HUMANGATE_PROXY_TARGET ||
    'https://orchestrator-production-7346.up.railway.app';
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/humangate': {
          target: proxyTarget,
          changeOrigin: true,
          secure: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  };
});
