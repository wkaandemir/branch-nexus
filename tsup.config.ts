import { defineConfig } from 'tsup';

export default defineConfig({
  entry: {
    cli: 'ts-src/cli.ts',
    index: 'ts-src/index.ts',
  },
  format: ['esm'],
  platform: 'node',
  target: 'node18',
  clean: true,
  dts: true,
  sourcemap: true,
  minify: false,
  shims: true,
  splitting: false,
  treeshake: true,
  external: [
    'inquirer',
    'chalk',
    'ora',
    'conf',
    'simple-git',
    'execa',
    'zod',
    'commander',
  ],
  outExtension() {
    return {
      js: '.js',
    };
  },
});
