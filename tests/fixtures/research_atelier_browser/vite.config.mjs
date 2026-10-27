import { fileURLToPath } from 'node:url';
import { defineConfig } from '../../../web-ui/node_modules/vite/dist/node/index.js';
import react from '../../../web-ui/node_modules/@vitejs/plugin-react/dist/index.js';

const ui = fileURLToPath(new URL('../../../web-ui/', import.meta.url));
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)), plugins: [react()],
  resolve: { alias: { '@': ui + 'src', react: ui + 'node_modules/react', 'react-dom': ui + 'node_modules/react-dom' } },
  css: { postcss: ui },
  server: { host: '127.0.0.1', port: 43281, strictPort: true,
    fs: { allow: [fileURLToPath(new URL('../../../', import.meta.url))] } },
});
