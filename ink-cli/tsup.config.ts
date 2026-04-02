import {defineConfig} from 'tsup';

export default defineConfig({
  entry: ['src/main.tsx'],
  format: ['esm'],
  target: 'node18',
  bundle: true,
  sourcemap: true,
  banner: {
    js: '#!/usr/bin/env node'
  }
});
