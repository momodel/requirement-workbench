import type { ArtifactRecord, ProjectState, StateItem } from '../../lib/types';

export const WORKBENCH_STAGE_ORDER = [
  'intake',
  'business_understanding',
  'requirement_alignment',
  'solution_definition',
  'design_delivery',
] as const;

export type WorkbenchStage = (typeof WORKBENCH_STAGE_ORDER)[number];

export const WORKBENCH_STAGE_LABELS: Record<WorkbenchStage, string> = {
  intake: '需求接入',
  business_understanding: '业务理解',
  requirement_alignment: '需求收敛',
  solution_definition: '方案定义',
  design_delivery: '设计交付',
};

export type DerivedStageState = {
  primaryStage: WorkbenchStage;
  revisitingStages: WorkbenchStage[];
};

export type StateOverviewItemKind = 'state' | 'artifact';

export type StateOverviewItem = {
  id: string;
  kind: StateOverviewItemKind;
  title: string;
  body: string;
  status: string;
  updatedAt: string | null;
  sourceCount: number;
  formedStage: WorkbenchStage;
  updatedStage: WorkbenchStage;
  isRecent: boolean;
  artifactType?: ArtifactRecord['artifact_type'];
  contentFormat?: string;
  previewUrl?: string | null;
  documentBody?: string | null;
};

export type ArtifactStatusSummary = {
  generating: number;
  generated: number;
  failed: number;
};

export type StateOverviewSection = {
  id: string;
  title: string;
  description: string;
  items: StateOverviewItem[];
  totalCount: number;
  recentCount: number;
  updatedAt: string | null;
  artifactStatusSummary?: ArtifactStatusSummary;
};

const STAGE_INDEX = Object.fromEntries(
  WORKBENCH_STAGE_ORDER.map((stage, index) => [stage, index])
) as Record<WorkbenchStage, number>;

const CATEGORY_STAGE_MAP: Record<string, WorkbenchStage> = {
  versions: 'requirement_alignment',
  artifacts: 'design_delivery',
  current_understanding: 'business_understanding',
  pending_items: 'requirement_alignment',
  confirmed_items: 'requirement_alignment',
  conflict_items: 'requirement_alignment',
  mvp_items: 'solution_definition',
};

function compareUpdatedAtDesc(
  left: { updatedAt: string | null },
  right: { updatedAt: string | null }
) {
  return toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt);
}

function toTimestamp(value: string | null | undefined) {
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function getStateStageByCategory(category: string | null | undefined) {
  if (!category) return 'business_understanding' as WorkbenchStage;
  return CATEGORY_STAGE_MAP[category] ?? 'business_understanding';
}

function getArtifactStage(_: ArtifactRecord) {
  return 'design_delivery' as WorkbenchStage;
}

function isStateItemRecent(item: StateItem, recentInsightIds: string[]) {
  return recentInsightIds.includes(item.id);
}

function buildStateOverviewItem(
  item: StateItem,
  recentInsightIds: string[],
  stageOverride?: WorkbenchStage
): StateOverviewItem {
  const inferredStage =
    stageOverride ?? getStateStageByCategory(item.category);

  return {
    id: item.id,
    kind: 'state',
    title: item.title,
    body: item.body,
    status: item.status,
    updatedAt: item.updated_at,
    sourceCount: item.source_ids.length,
    formedStage: inferredStage,
    updatedStage: inferredStage,
    isRecent: isStateItemRecent(item, recentInsightIds),
  };
}


function getLatestArtifactsByType(artifacts: ArtifactRecord[]) {
  const latestByType = new Map<string, ArtifactRecord>();
  for (const artifact of artifacts) {
    const existing = latestByType.get(artifact.artifact_type);
    if (!existing || toTimestamp(artifact.updated_at) > toTimestamp(existing.updated_at)) {
      latestByType.set(artifact.artifact_type, artifact);
    }
  }
  return Array.from(latestByType.values());
}

function getArtifactStatusSummary(items: StateOverviewItem[]): ArtifactStatusSummary {
  return items.reduce<ArtifactStatusSummary>(
    (summary, item) => {
      if (item.status === 'generating') summary.generating += 1;
      else if (item.status === 'failed') summary.failed += 1;
      else if (item.status === 'generated') summary.generated += 1;
      return summary;
    },
    { generating: 0, generated: 0, failed: 0 }
  );
}

function buildArtifactOverviewItem(
  artifact: ArtifactRecord,
  recentArtifactIds: string[]
): StateOverviewItem {
  const stage = getArtifactStage(artifact);
  return {
    id: artifact.id,
    kind: 'artifact',
    title: artifact.title,
    body: artifact.summary,
    status: artifact.status,
    updatedAt: artifact.updated_at,
    sourceCount: 0,
    formedStage: stage,
    updatedStage: stage,
    isRecent: recentArtifactIds.includes(artifact.id),
    artifactType: artifact.artifact_type,
    contentFormat: artifact.content_format,
    previewUrl: artifact.preview_url,
    documentBody: artifact.body,
  };
}

function getPrimaryStage(state: ProjectState) {
  const artifactCount = state.artifacts.length;
  if (artifactCount > 0) return 'design_delivery' as WorkbenchStage;
  if (state.mvp_items.length > 0) return 'solution_definition' as WorkbenchStage;
  if (
    state.confirmed_items.length > 0 ||
    state.conflict_items.length > 0 ||
    state.pending_items.length > 0
  ) {
    return 'requirement_alignment' as WorkbenchStage;
  }
  if (state.current_understanding.length > 0) return 'business_understanding' as WorkbenchStage;
  return 'intake' as WorkbenchStage;
}

function collectRecentItems(state: ProjectState, recentInsightIds: string[]) {
  const allItems = [
    ...state.current_understanding,
    ...state.pending_items,
    ...state.confirmed_items,
    ...state.conflict_items,
    ...state.mvp_items,
    ...state.versions,
    ...state.artifacts,
  ];

  return allItems.filter((item) => recentInsightIds.includes(item.id));
}

function addRevisit(target: WorkbenchStage[], stage: WorkbenchStage) {
  if (!target.includes(stage)) {
    target.push(stage);
  }
}

export function deriveStageState(
  state: ProjectState,
  recentInsightIds: string[] = []
): DerivedStageState {
  const primaryStage = getPrimaryStage(state);
  const revisitingStages: WorkbenchStage[] = [];
  const recentItems = collectRecentItems(state, recentInsightIds);

  const hasRecentPending = recentItems.some((item) => item.category === 'pending_items');
  const hasRecentConflict = recentItems.some((item) => item.category === 'conflict_items');
  const hasPendingItems = state.pending_items.length > 0;
  const hasConflictItems = state.conflict_items.length > 0;

  if (
    STAGE_INDEX[primaryStage] >= STAGE_INDEX.requirement_alignment &&
    (hasRecentPending || hasPendingItems)
  ) {
    addRevisit(revisitingStages, 'business_understanding');
  }

  if (
    STAGE_INDEX[primaryStage] >= STAGE_INDEX.solution_definition &&
    (hasRecentConflict || hasConflictItems)
  ) {
    addRevisit(revisitingStages, 'requirement_alignment');
  }

  if (
    primaryStage === 'design_delivery' &&
    (hasRecentPending || hasRecentConflict || hasPendingItems || hasConflictItems)
  ) {
    addRevisit(revisitingStages, 'requirement_alignment');
  }

  revisitingStages.sort((left, right) => STAGE_INDEX[left] - STAGE_INDEX[right]);

  return { primaryStage, revisitingStages };
}

function buildOverviewSection(
  id: string,
  title: string,
  description: string,
  items: StateOverviewItem[]
): StateOverviewSection {
  const sortedItems = [...items].sort(compareUpdatedAtDesc);
  return {
    id,
    title,
    description,
    items: sortedItems,
    totalCount: sortedItems.length,
    recentCount: sortedItems.filter((item) => item.isRecent).length,
    updatedAt: sortedItems[0]?.updatedAt ?? null,
  };
}

export function deriveStateOverviewSections(
  state: ProjectState,
  artifacts: ArtifactRecord[],
  recentInsightIds: string[] = []
): StateOverviewSection[] {
  const artifactItems = getLatestArtifactsByType(artifacts).map((artifact) =>
    buildArtifactOverviewItem(artifact, recentInsightIds)
  );

  return [
    buildOverviewSection(
      'current_definition',
      '当前需求定义',
      '当前主线理解与问题定义。',
      state.current_understanding.map((item) => buildStateOverviewItem(item, recentInsightIds))
    ),
    buildOverviewSection(
      'pending_items',
      '关键待确认',
      '还需要客户确认的边界、口径和规则。',
      state.pending_items.map((item) => buildStateOverviewItem(item, recentInsightIds))
    ),
    buildOverviewSection(
      'risk_conflicts',
      '风险与冲突',
      '当前识别出的冲突、风险和不一致点。',
      state.conflict_items.map((item) => buildStateOverviewItem(item, recentInsightIds))
    ),
    buildOverviewSection(
      'mvp_items',
      'MVP 结论',
      '当前已形成的方案方向和 MVP 收敛结论。',
      state.mvp_items.map((item) => buildStateOverviewItem(item, recentInsightIds))
    ),
    {
      ...buildOverviewSection(
        'artifacts',
        '交付物',
        '文档稿、页面方案和交互稿等产物。',
        artifactItems
      ),
      artifactStatusSummary: getArtifactStatusSummary(artifactItems),
    },
    buildOverviewSection(
      'versions',
      '版本快照',
      '关键轮次自动生成的状态快照。',
      state.versions.map((item) => buildStateOverviewItem(item, recentInsightIds))
    ),
  ];
}
