// @vitest-environment node

import { readFileSync } from 'node:fs';

describe('index.html', () => {
  test('registers a favicon link', () => {
    const html = readFileSync('index.html', 'utf8');

    expect(html).toContain('rel="icon"');
    expect(html).toContain('href="/favicon.svg"');
  });
});
