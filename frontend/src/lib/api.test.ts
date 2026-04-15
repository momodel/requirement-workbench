import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createProject,
  createUrlSource,
  createFileSource,
  createTextSource,
  generateArtifact,
  getArtifactContent,
  getProject,
  getProjectState,
  listArtifacts,
  listProjects,
  listSources,
  sendChatRound
} from './api';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe('api client', () => {
  it('maps backend responses when fetch succeeds', async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith('/api/projects')) {
        return new Response(
          JSON.stringify([
            {
              id: 'seed-reconciliation',
              name: '业财逐笔对账',
              summary: '真实后端返回',
              status: 'seed',
              scenario_type: 'financial-reconciliation',
              updated_at: '2026-04-15T10:00:00+08:00'
            }
          ])
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation')) {
        return new Response(
          JSON.stringify({
            id: 'seed-reconciliation',
            name: '业财逐笔对账',
            summary: '真实后端返回',
            status: 'seed',
            scenario_type: 'financial-reconciliation',
            updated_at: '2026-04-15T10:00:00+08:00'
          })
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/sources')) {
        return new Response(
          JSON.stringify([
            {
              id: 'src-1',
              name: '访谈纪要.txt',
              source_kind: 'text',
              upload_kind: 'text',
              storage_path: '/tmp/source.txt',
              normalized_path: '/tmp/normalized.md',
              parse_status: 'parsed',
              parse_summary: '这里是摘要',
              sync_status: 'pending'
            }
          ])
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/state')) {
        return new Response(
          JSON.stringify({
            current_understanding: [{ id: 'u1', title: '理解', body: '真实状态' }],
            pending_items: [],
            confirmed_items: [],
            conflict_items: [],
            mvp_items: [],
            versions: [],
            artifacts: []
          })
        );
      }

      return new Response('Not found', { status: 404 });
    }) as typeof fetch;

    const projects = await listProjects();
    const project = await getProject('seed-reconciliation');
    const sources = await listSources('seed-reconciliation');
    const state = await getProjectState('seed-reconciliation');

    expect(projects[0].scenarioType).toBe('financial-reconciliation');
    expect(project.updatedAt).toBe('2026-04-15T10:00:00+08:00');
    expect(sources[0].sourceKind).toBe('text');
    expect(sources[0].parseSummary).toBe('这里是摘要');
    expect(state.currentUnderstanding[0].body).toBe('真实状态');
  });

  it('falls back to seed data when fetch fails', async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error('network down');
    }) as typeof fetch;

    const projects = await listProjects();
    const project = await getProject('seed-reconciliation');
    const sources = await listSources('seed-reconciliation');
    const state = await getProjectState('seed-reconciliation');

    expect(projects[0].id).toBe('seed-reconciliation');
    expect(project.name).toBe('业财逐笔对账');
    expect(sources).toHaveLength(2);
    expect(state.pendingItems[0].title).toContain('接入真实 SSE');
  });

  it('creates sources, parses chat events, and reads artifacts through backend APIs', async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith('/api/projects') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            id: 'project-new',
            name: '结算对账分析',
            summary: '新建项目',
            status: 'draft',
            scenario_type: 'settlement-reconciliation',
            updated_at: '2026-04-15T10:00:00+08:00'
          })
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/sources')) {
        const body = JSON.parse(String(init?.body ?? '{}'));
        return new Response(
          JSON.stringify({
            id: `src-${body.upload_kind}`,
            name: body.name,
            source_kind: body.source_kind ?? body.upload_kind,
            upload_kind: body.upload_kind,
            storage_path: '/tmp/source.bin',
            normalized_path: '/tmp/normalized.md',
            parse_status: 'parsed',
            parse_summary: '已生成摘要',
            sync_status: 'pending'
          })
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/chat/stream')) {
        return new Response(
          [
            'event: message_chunk',
            'data: {"project_id":"seed-reconciliation","text":"第一段。"}',
            '',
            'event: citations',
            'data: {"project_id":"seed-reconciliation","items":[{"source_id":"src-text","source_name":"补充纪要.txt","excerpt":"摘要","quote":"引文"}]}',
            '',
            'event: version_patch',
            'data: {"project_id":"seed-reconciliation","op":"upsert","items":[{"id":"v1","title":"chat-round","body":"生成快照"}]}',
            '',
            'event: done',
            'data: {"project_id":"seed-reconciliation"}',
            ''
          ].join('\n')
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/artifacts/generate')) {
        return new Response(
          JSON.stringify({
            id: 'artifact-1',
            project_id: 'seed-reconciliation',
            artifact_type: 'document',
            title: '需求分析文档稿',
            summary: '结构化文档',
            status: 'generated',
            content_format: 'json',
            storage_path: '/tmp/artifact.json'
          })
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/artifacts')) {
        return new Response(
          JSON.stringify([
            {
              id: 'artifact-1',
              project_id: 'seed-reconciliation',
              artifact_type: 'document',
              title: '需求分析文档稿',
              summary: '结构化文档',
              status: 'generated',
              content_format: 'json',
              storage_path: '/tmp/artifact.json'
            }
          ])
        );
      }

      if (url.endsWith('/api/projects/seed-reconciliation/artifacts/artifact-1/content')) {
        return new Response(JSON.stringify({ title: '需求分析文档稿', sections: [] }));
      }

      return new Response('Not found', { status: 404 });
    }) as typeof fetch;

    const project = await createProject('结算对账分析', '新建项目', 'settlement-reconciliation');
    const source = await createTextSource('seed-reconciliation', '补充纪要.txt', '这里是补充文本');
    const urlSource = await createUrlSource(
      'seed-reconciliation',
      '业务链接',
      'https://example.com'
    );
    const file = new File(['binary'], '样本.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    });
    const fileSource = await createFileSource('seed-reconciliation', file);
    const events = await sendChatRound('seed-reconciliation', '请总结一下');
    const artifact = await generateArtifact('seed-reconciliation', 'document');
    const artifacts = await listArtifacts('seed-reconciliation');
    const artifactContent = await getArtifactContent('seed-reconciliation', 'artifact-1');

    expect(project.id).toBe('project-new');
    expect(source.id).toBe('src-text');
    expect(urlSource.id).toBe('src-url');
    expect(fileSource.id).toBe('src-file');
    expect(events[0].event).toBe('message_chunk');
    expect(events[1].event).toBe('citations');
    expect(artifact.id).toBe('artifact-1');
    expect(artifacts).toHaveLength(1);
    expect(artifactContent).toContain('需求分析文档稿');
  });
});
