import { describe, expect, it } from 'vitest';

import type { ArtifactRecord, ProjectState } from '../../lib/types';
import {
  deriveStageState,
  deriveStateOverviewSections,
} from './workbench-derived';

function createEmptyState(): ProjectState {
  return {
    current_understanding: [],
    pending_items: [],
    confirmed_items: [],
    conflict_items: [],
    mvp_items: [],
    versions: [],
    artifacts: [],
  };
}

describe('workbench-derived', () => {
  it('derives primary stage from current project state and reopens earlier stages when new conflicts appear', () => {
    const state = createEmptyState();
    state.current_understanding = [
      {
        id: 'understanding-1',
        title: '当前需求定义',
        body: '先确认逐笔对账范围。',
        status: 'active',
        category: 'current_understanding',
        updated_at: '2026-04-20T18:00:00+08:00',
        source_ids: ['src-1'],
      },
    ];
    state.confirmed_items = [
      {
        id: 'confirmed-1',
        title: '对账粒度',
        body: '一期按逐笔对账推进。',
        status: 'confirmed',
        category: 'confirmed_items',
        updated_at: '2026-04-20T18:05:00+08:00',
        source_ids: ['src-1'],
      },
    ];
    state.mvp_items = [
      {
        id: 'mvp-1',
        title: 'MVP 结论',
        body: '先做差异识别与人工确认闭环。',
        status: 'active',
        category: 'mvp_items',
        updated_at: '2026-04-20T18:10:00+08:00',
        source_ids: ['src-1'],
      },
    ];
    state.conflict_items = [
      {
        id: 'conflict-1',
        title: '退款口径冲突',
        body: '业务与财务对退款科目挂接口径不一致。',
        status: 'active',
        category: 'conflict_items',
        updated_at: '2026-04-20T18:12:00+08:00',
        source_ids: ['src-2'],
      },
    ];

    const derived = deriveStageState(state, ['conflict-1']);

    expect(derived.primaryStage).toBe('solution_definition');
    expect(derived.revisitingStages).toEqual(['requirement_alignment']);
  });

  it('groups project state into overview sections for the right sidebar', () => {
    const state = createEmptyState();
    state.current_understanding = [
      {
        id: 'understanding-1',
        title: '当前需求定义',
        body: '先完成逐笔对账与财务科目映射确认。',
        status: 'active',
        category: 'current_understanding',
        updated_at: '2026-04-20T18:00:00+08:00',
        source_ids: ['src-1'],
      },
    ];
    state.pending_items = [
      {
        id: 'pending-1',
        title: '退款处理边界',
        body: '需要明确是否纳入一期自动归类。',
        status: 'active',
        category: 'pending_items',
        updated_at: '2026-04-20T18:06:00+08:00',
        source_ids: ['src-2'],
      },
    ];
    state.conflict_items = [
      {
        id: 'conflict-1',
        title: '税额拆分冲突',
        body: '订单系统与财务系统税额拆分规则不同。',
        status: 'active',
        category: 'conflict_items',
        updated_at: '2026-04-20T18:08:00+08:00',
        source_ids: ['src-3'],
      },
    ];
    state.mvp_items = [
      {
        id: 'mvp-1',
        title: 'MVP 结论',
        body: '先做差异识别、异常归类建议和人工确认。',
        status: 'active',
        category: 'mvp_items',
        updated_at: '2026-04-20T18:10:00+08:00',
        source_ids: ['src-1'],
      },
    ];
    state.versions = [
      {
        id: 'version-1',
        title: '需求收敛快照',
        body: '已形成逐笔对账范围与一期边界。',
        status: 'snapshot',
        category: 'versions',
        updated_at: '2026-04-20T18:12:00+08:00',
        source_ids: [],
      },
    ];

    const artifacts: ArtifactRecord[] = [
      {
        id: 'artifact-1',
        project_id: 'project-1',
        artifact_type: 'page_solution',
        title: '页面方案 v2',
        summary: '最新页面方案',
        status: 'generated',
        content_format: 'html',
        storage_path: '/tmp/page-v2.html',
        preview_url: '/preview/page-v2',
        body: null,
        updated_at: '2026-04-20T18:15:00+08:00',
      },
    ];

    const sections = deriveStateOverviewSections(state, artifacts);

    expect(sections.map((section) => section.title)).toEqual([
      '当前需求定义',
      '关键待确认',
      '风险与冲突',
      'MVP 结论',
      '交付物',
      '版本快照',
    ]);
    expect(sections[0].items[0]?.title).toBe('当前需求定义');
    expect(sections[4].items[0]?.title).toBe('页面方案 v2');
  });
});
