import { describe, expect, it } from 'vitest';

import {
  getArtifactDisplayLabel,
  getArtifactFormatLabel,
  getArtifactStatusLabel,
  getArtifactTypeLabel,
} from './artifact-display';

describe('artifact-display', () => {
  it('returns stable Chinese labels for artifact type and format', () => {
    expect(getArtifactTypeLabel('page_solution')).toBe('页面方案');
    expect(getArtifactFormatLabel('page_solution', 'html')).toBe('HTML 页面原型');
    expect(
      getArtifactDisplayLabel({
        artifact_type: 'interaction_flow',
        content_format: 'html',
      })
    ).toBe('交互稿（HTML 交互原型）');
  });

  it('returns readable Chinese status labels', () => {
    expect(getArtifactStatusLabel('generated')).toBe('已生成');
    expect(getArtifactStatusLabel('failed')).toBe('生成失败');
  });
});
