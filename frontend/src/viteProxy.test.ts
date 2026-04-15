// @vitest-environment node

import config from '../vite.config';

describe('vite dev server config', () => {
  test('proxies api requests to backend', () => {
    const proxy = config.server?.proxy;

    expect(proxy).toBeDefined();
    expect(typeof proxy).toBe('object');
    expect('/api' in (proxy ?? {})).toBe(true);

    const apiProxy = (proxy as Record<string, unknown>)['/api'];

    expect(apiProxy).toMatchObject({
      target: 'http://127.0.0.1:8000',
      changeOrigin: true
    });
  });
});
