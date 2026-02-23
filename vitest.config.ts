import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    exclude: ['node_modules', 'dist', 'src'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: [
        'tests/**',
        'dist/**',
        'src/**',
        'node_modules/**',
        '**/*.d.ts',
        '**/*.config.ts',
        'ts-src/cli.ts',
      ],
      all: true,
      lines: 80,
      functions: 80,
      branches: 70,
      statements: 80,
    },
    timeout: 10000,
    testTimeout: 5000,
    hookTimeout: 10000,
    reporters: ['default'],
    passWithNoTests: true,
  },
});
