import type { ArtifactRecord } from './types';

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  document: '文档稿',
  page_solution: '页面方案',
  interaction_flow: '交互稿',
  visual_mockup: '视觉稿',
};

const ARTIFACT_STATUS_LABELS: Record<string, string> = {
  generated: '已生成',
  generating: '生成中',
  failed: '生成失败',
};

export function getArtifactTypeLabel(artifactType: string) {
  return ARTIFACT_TYPE_LABELS[artifactType] ?? '其他产物';
}

export function getArtifactStatusLabel(status: string) {
  return ARTIFACT_STATUS_LABELS[status] ?? status;
}

export function getArtifactFormatLabel(
  artifactType: string,
  contentFormat: string | null | undefined
) {
  if (contentFormat === 'image') {
    return '图片预览';
  }

  if (contentFormat === 'html') {
    if (artifactType === 'page_solution') return 'HTML 页面原型';
    if (artifactType === 'interaction_flow') return 'HTML 交互原型';
    return 'HTML 预览';
  }

  if (contentFormat === 'markdown') {
    return '结构化文档';
  }

  return '内容预览';
}

export function getArtifactDisplayLabel(
  artifact: Pick<ArtifactRecord, 'artifact_type' | 'content_format'>
) {
  return `${getArtifactTypeLabel(artifact.artifact_type)}（${getArtifactFormatLabel(
    artifact.artifact_type,
    artifact.content_format
  )}）`;
}
