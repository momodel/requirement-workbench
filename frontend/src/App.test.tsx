import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import App from './App';

type JsonResponse = Record<string, unknown> | Array<unknown>;

function installFetchMock(routes: Record<string, JsonResponse>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const path = new URL(url, 'http://localhost').pathname;
    const payload = routes[path];

    if (!payload) {
      return new Response(`Unhandled request for ${path}`, { status: 404 });
    }

    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

describe('App', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/');
  });

  it('renders the projects home page from the API payload', async () => {
    installFetchMock({
      '/api/projects': [
        {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账',
          scenario_type: 'reconciliation',
          summary: '演示项目',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
      ],
      '/api/providers/readiness': {
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'knowledge_base_missing',
          summary: '项目级证据运行时还没有初始化项目知识库。',
          detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
          action_label: '初始化项目知识库',
        },
      },
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '客户需求转译台' })).toBeInTheDocument();
    expect(await screen.findByText('集团业财逐笔对账')).toBeInTheDocument();
    expect(screen.getByText('选择一个项目进入工作台')).toBeInTheDocument();
    expect(screen.getByText('Runtime Readiness')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新建项目' })).toBeInTheDocument();
  });

  it('creates a project from the home page and navigates into the new workbench', async () => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });

    let knowledgeBaseReady = false;
    let createdProject:
      | {
          id: string;
          name: string;
          scenario_type: string;
          summary: string;
          status: string;
          created_at: string;
          updated_at: string;
          seed_key: null;
        }
      | null = null;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/project-created-001/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        return new Response(
          JSON.stringify({
            id: 'kb-created-001',
            project_id: 'project-created-001',
            provider: 'QDRANT_LLAMAINDEX',
            external_knowledge_base_id: 'project-created-001',
            display_name: '渠道对账需求分析',
            description: null,
            status: 'ready',
            status_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
            updated_at: '2026-04-16T00:00:00+08:00',
          }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }

      if (path === '/api/projects' && method === 'POST') {
        const body = JSON.parse(String(init?.body ?? '{}')) as {
          name: string;
          scenario_type: string;
          summary: string;
        };
        createdProject = {
          id: 'project-created-001',
          name: body.name,
          scenario_type: body.scenario_type,
          summary: body.summary,
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: null,
        };
        return new Response(JSON.stringify(createdProject), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects': createdProject
          ? [createdProject]
          : [
              {
                id: 'seed-reconciliation',
                name: '集团业财逐笔对账',
                scenario_type: 'reconciliation',
                summary: '演示项目',
                status: 'active',
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
                seed_key: 'seed-reconciliation',
              },
            ],
        '/api/providers/readiness': {
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '项目内证据运行时已就绪。',
            detail: null,
            action_label: null,
          },
        },
        '/api/projects/project-created-001': createdProject ?? {
          id: 'project-created-001',
          name: '新项目',
          scenario_type: 'financial-reconciliation',
          summary: '新项目摘要',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: null,
        },
        '/api/projects/project-created-001/sources': [],
        '/api/projects/project-created-001/messages': [],
        '/api/projects/project-created-001/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/project-created-001/readiness': {
          project_id: 'project-created-001',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: project-created-001; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-created-001',
                project_id: 'project-created-001',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-created-001',
                display_name: '渠道对账需求分析',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
        },
        '/api/projects/project-created-001/knowledge-base': {
          project_id: 'project-created-001',
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-created-001',
                project_id: 'project-created-001',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-created-001',
                display_name: '渠道对账需求分析',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: project-created-001; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/project-created-001/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: '新建项目' }));
    await user.type(screen.getByPlaceholderText('例如：集团业财逐笔对账需求分析'), '渠道对账需求分析');
    await user.type(screen.getByPlaceholderText('例如：financial-reconciliation'), 'channel-reconciliation');
    await user.type(
      screen.getByPlaceholderText('用一句话说明这个项目想解决什么问题。'),
      '分析渠道业务与财务入账之间的逐笔核对需求。'
    );
    await user.click(screen.getByRole('button', { name: '创建并进入工作台' }));

    expect(await screen.findByRole('heading', { name: '渠道对账需求分析' })).toBeInTheDocument();
    expect(await screen.findByText('Evidence: 已就绪')).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/projects',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/projects/project-created-001/knowledge-base/init',
      expect.objectContaining({
        method: 'POST',
      })
    );
  });

  it('auto-initializes the knowledge base when entering an existing uninitialized project workbench', async () => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });

    window.history.replaceState({}, '', '/projects/project-legacy-001/workbench');

    let knowledgeBaseReady = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/project-legacy-001/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        return new Response(
          JSON.stringify({
            id: 'kb-legacy-001',
            project_id: 'project-legacy-001',
            provider: 'QDRANT_LLAMAINDEX',
            external_knowledge_base_id: 'project-legacy-001',
            display_name: '历史需求分析项目',
            description: null,
            status: 'ready',
            status_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
            updated_at: '2026-04-16T00:00:00+08:00',
          }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/project-legacy-001': {
          id: 'project-legacy-001',
          name: '历史需求分析项目',
          scenario_type: 'general',
          summary: '一个之前创建但还没绑定 notebook 的项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: null,
        },
        '/api/projects/project-legacy-001/sources': [],
        '/api/projects/project-legacy-001/messages': [],
        '/api/projects/project-legacy-001/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/project-legacy-001/readiness': {
          project_id: 'project-legacy-001',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: project-legacy-001; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-legacy-001',
                project_id: 'project-legacy-001',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-legacy-001',
                display_name: '历史需求分析项目',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
        },
        '/api/projects/project-legacy-001/knowledge-base': {
          project_id: 'project-legacy-001',
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-legacy-001',
                project_id: 'project-legacy-001',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-legacy-001',
                display_name: '历史需求分析项目',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: project-legacy-001; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/project-legacy-001/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '历史需求分析项目' })).toBeInTheDocument();

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/projects/project-legacy-001/knowledge-base/init',
        expect.objectContaining({
          method: 'POST',
        })
      );
    });

    expect(await screen.findByText('Evidence: 已就绪')).toBeInTheDocument();
  });

  it('normalizes legacy binding_required readiness into knowledge base initialization flow', async () => {
    window.history.replaceState({}, '', '/projects/project-legacy-binding/workbench');

    let knowledgeBaseReady = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/project-legacy-binding/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        return new Response(
          JSON.stringify({
            id: 'kb-legacy-binding',
            project_id: 'project-legacy-binding',
            provider: 'QDRANT_LLAMAINDEX',
            external_knowledge_base_id: 'project-legacy-binding',
            display_name: '历史绑定项目',
            description: null,
            status: 'ready',
            status_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
            updated_at: '2026-04-16T00:00:00+08:00',
          }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/project-legacy-binding': {
          id: 'project-legacy-binding',
          name: '历史绑定项目',
          scenario_type: 'general',
          summary: '旧项目返回了 notebook-era readiness。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: null,
        },
        '/api/projects/project-legacy-binding/sources': [],
        '/api/projects/project-legacy-binding/messages': [],
        '/api/projects/project-legacy-binding/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/project-legacy-binding/readiness': {
          project_id: 'project-legacy-binding',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'binding_required',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '历史接口仍返回待绑定状态。',
            detail: knowledgeBaseReady ? 'Collection: project-legacy-binding; indexed chunks: 0' : 'legacy binding_required should be treated as knowledge_base_missing.',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-legacy-binding',
                project_id: 'project-legacy-binding',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-legacy-binding',
                display_name: '历史绑定项目',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
        },
        '/api/projects/project-legacy-binding/knowledge-base': {
          project_id: 'project-legacy-binding',
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-legacy-binding',
                project_id: 'project-legacy-binding',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-legacy-binding',
                display_name: '历史绑定项目',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'binding_required',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '历史接口仍返回待绑定状态。',
            detail: knowledgeBaseReady ? 'Collection: project-legacy-binding; indexed chunks: 0' : 'legacy binding_required should be treated as knowledge_base_missing.',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/project-legacy-binding/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '历史绑定项目' })).toBeInTheDocument();

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/projects/project-legacy-binding/knowledge-base/init',
        expect.objectContaining({
          method: 'POST',
        })
      );
    });

    expect(await screen.findByText('Evidence: 已就绪')).toBeInTheDocument();
  });

  it('falls back to legacy notebooklm readiness payloads and still auto-initializes the knowledge base', async () => {
    window.history.replaceState({}, '', '/projects/project-legacy-notebooklm/workbench');

    let knowledgeBaseReady = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/project-legacy-notebooklm/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        return new Response(
          JSON.stringify({
            id: 'kb-legacy-notebooklm',
            project_id: 'project-legacy-notebooklm',
            provider: 'QDRANT_LLAMAINDEX',
            external_knowledge_base_id: 'project-legacy-notebooklm',
            display_name: '历史 NotebookLM 项目',
            description: null,
            status: 'ready',
            status_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
            updated_at: '2026-04-16T00:00:00+08:00',
          }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/project-legacy-notebooklm': {
          id: 'project-legacy-notebooklm',
          name: '历史 NotebookLM 项目',
          scenario_type: 'general',
          summary: '旧项目仍返回 notebooklm readiness 字段。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: null,
        },
        '/api/projects/project-legacy-notebooklm/sources': [],
        '/api/projects/project-legacy-notebooklm/messages': [],
        '/api/projects/project-legacy-notebooklm/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/project-legacy-notebooklm/readiness': knowledgeBaseReady
          ? {
              project_id: 'project-legacy-notebooklm',
              claude: {
                provider: 'CLAUDE_AGENT_SDK',
                status: 'ready',
                summary: 'Claude Agent SDK 已就绪。',
                detail: null,
                action_label: null,
              },
              notebooklm: {
                provider: 'QDRANT_LLAMAINDEX',
                status: 'ready',
                summary: '当前项目知识库可用于证据检索。',
                detail: 'Collection: project-legacy-notebooklm; indexed chunks: 0',
                action_label: null,
              },
              knowledge_base: {
                id: 'kb-legacy-notebooklm',
                project_id: 'project-legacy-notebooklm',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-legacy-notebooklm',
                display_name: '历史 NotebookLM 项目',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              },
            }
          : {
              project_id: 'project-legacy-notebooklm',
              claude: {
                provider: 'CLAUDE_AGENT_SDK',
                status: 'ready',
                summary: 'Claude Agent SDK 已就绪。',
                detail: null,
                action_label: null,
              },
              notebooklm: {
                provider: 'QDRANT_LLAMAINDEX',
                status: 'binding_required',
                summary: '旧接口仍只返回 notebooklm 待绑定状态。',
                detail: 'legacy notebooklm readiness should normalize into knowledge_base_missing.',
                action_label: '初始化知识库',
              },
              knowledge_base: null,
            },
        '/api/projects/project-legacy-notebooklm/knowledge-base': {
          project_id: 'project-legacy-notebooklm',
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-legacy-notebooklm',
                project_id: 'project-legacy-notebooklm',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'project-legacy-notebooklm',
                display_name: '历史 NotebookLM 项目',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady
              ? 'Collection: project-legacy-notebooklm; indexed chunks: 0'
              : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/project-legacy-notebooklm/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '历史 NotebookLM 项目' })).toBeInTheDocument();

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/projects/project-legacy-notebooklm/knowledge-base/init',
        expect.objectContaining({
          method: 'POST',
        })
      );
    });

    expect(await screen.findByText('Evidence: 已就绪')).toBeInTheDocument();
  });

  it('renders the workbench with project, sources, messages and state from the API payload', async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });

    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    installFetchMock({
      '/api/projects/seed-reconciliation': {
        id: 'seed-reconciliation',
        name: '集团业财逐笔对账需求分析',
        scenario_type: 'reconciliation',
        summary: '默认 seed 项目。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: 'seed-reconciliation',
      },
      '/api/projects/seed-reconciliation/sources': [
        {
          id: 'src-1',
          project_id: 'seed-reconciliation',
          name: '财务口径说明',
          source_kind: 'document',
          upload_kind: 'seed',
          storage_path: null,
          normalized_path: null,
          index_input_mode: null,
          normalize_status: 'parsed',
          normalize_summary: '解释业务字段到财务科目的映射口径。',
          index_status: 'pending',
          index_error: null,
          created_at: '2026-04-16T00:00:00+08:00',
        },
      ],
      '/api/projects/seed-reconciliation/messages': [
        {
          id: 'msg-1',
          role: 'assistant',
          content: '我先把逐笔对账的真实矛盾拆开。',
          source_refs: [{ title: '财务口径说明' }],
          created_at: '2026-04-16T00:00:00+08:00',
          stream_group_id: null,
        },
      ],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [
          {
            id: 'state-1',
            title: '核心矛盾',
            body: '业务字段与财务科目映射不一致。',
            status: 'active',
            category: 'current_understanding',
            updated_at: '2026-04-16T00:00:00+08:00',
            source_ids: ['src-1'],
          },
        ],
        pending_items: [],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/seed-reconciliation/readiness': {
        project_id: 'seed-reconciliation',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'ready',
          summary: '当前项目知识库可用于证据检索。',
          detail: 'Collection: seed-reconciliation; indexed chunks: 2',
          action_label: null,
        },
      },
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' })).toBeInTheDocument();
    expect(await screen.findByText('项目知识库')).toBeInTheDocument();
    expect((await screen.findAllByText('财务口径说明')).length).toBeGreaterThan(0);
    expect(await screen.findByText('我先把逐笔对账的真实矛盾拆开。')).toBeInTheDocument();
    expect(await screen.findByText('核心矛盾')).toBeInTheDocument();
    expect(await screen.findByText('Stage 1')).toBeInTheDocument();
    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.getByTestId('sources-panel-content')).toHaveClass('flex', 'flex-1', 'flex-col');
    expect(screen.getByTestId('sources-scroll-area')).toHaveClass('overflow-y-auto');
    expect(screen.getByRole('button', { name: '导入文本资料' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上传文件' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '项目列表' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('button', { name: '运行状态' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '删除 财务口径说明' })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('资料名称')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('粘贴纪要、需求原话或规则说明。')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledTimes(7);
    });
  });

  it('renders canonical source indexing semantics in the workbench UI', async () => {
    window.history.replaceState({}, '', '/projects/source-status-priority/workbench');

    installFetchMock({
      '/api/projects/source-status-priority': {
        id: 'source-status-priority',
        name: '索引状态优先级验证',
        scenario_type: 'reconciliation',
        summary: '验证 source UI 以 canonical index_status 为主。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: null,
      },
      '/api/projects/source-status-priority/sources': [
        {
          id: 'src-canonical-pending',
          project_id: 'source-status-priority',
          name: '尚未入库资料',
          source_kind: 'document',
          upload_kind: 'file',
          storage_path: null,
          normalized_path: null,
          index_input_mode: 'docling',
          normalize_status: 'parsed',
          normalize_summary: '已完成标准化。',
          index_status: 'pending',
          index_error: null,
          created_at: '2026-04-16T00:00:00+08:00',
        },
      ],
      '/api/projects/source-status-priority/messages': [],
      '/api/projects/source-status-priority/state': {
        current_understanding: [],
        pending_items: [],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/source-status-priority/readiness': {
        project_id: 'source-status-priority',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'ready',
          summary: '当前项目知识库可用于证据检索。',
          detail: 'Collection: source-status-priority; indexed chunks: 0',
          action_label: null,
        },
      },
      '/api/projects/source-status-priority/artifacts': [],
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '索引状态优先级验证' })).toBeInTheDocument();
    expect(screen.getByText('1 份 · 0 已入库 · 1 待处理')).toBeInTheDocument();
    expect(screen.getAllByText('待入库').length).toBeGreaterThan(0);
    expect(screen.queryByText('1 份 · 1 已入库 · 1 待处理')).not.toBeInTheDocument();
  });

  it('shows a clear notice when source reindex returns a legacy-only payload', async () => {
    window.history.replaceState({}, '', '/projects/source-payload-contract/workbench');

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/source-payload-contract/sources/src-legacy-only/reindex' && method === 'POST') {
        return new Response(
          JSON.stringify({
            id: 'src-legacy-only',
            project_id: 'source-payload-contract',
            name: '旧资料',
            source_kind: 'document',
            upload_kind: 'file',
            storage_path: null,
            normalized_path: null,
            notebook_import_mode: null,
            parse_status: 'parsed',
            parse_summary: '旧 source payload',
            sync_status: 'synced',
            sync_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/source-payload-contract': {
          id: 'source-payload-contract',
          name: 'Source Payload Contract',
          scenario_type: 'reconciliation',
          summary: '验证 source transport 必须使用 canonical payload。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: null,
        },
        '/api/projects/source-payload-contract/sources': [
          {
            id: 'src-legacy-only',
            project_id: 'source-payload-contract',
            name: '旧资料',
            source_kind: 'document',
            upload_kind: 'file',
            storage_path: null,
            normalized_path: null,
            index_input_mode: null,
            normalize_status: 'parsed',
            normalize_summary: '当前仍然需要重新入库。',
            index_status: 'index_failed',
            index_error: '首次入库失败',
            created_at: '2026-04-16T00:00:00+08:00',
          },
        ],
        '/api/projects/source-payload-contract/messages': [],
        '/api/projects/source-payload-contract/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/source-payload-contract/readiness': {
          project_id: 'source-payload-contract',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '当前项目知识库可用于证据检索。',
            detail: 'Collection: source-payload-contract; indexed chunks: 1',
            action_label: null,
          },
        },
        '/api/projects/source-payload-contract/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText('入库失败')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试入库 旧资料' }));

    expect(await screen.findByText('重建索引失败')).toBeInTheDocument();
    expect(screen.getByText('入库失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试入库 旧资料' })).toBeInTheDocument();
  });

  it('navigates back to the projects list from the workbench header', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    installFetchMock({
      '/api/projects': [
        {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账',
          scenario_type: 'reconciliation',
          summary: '演示项目',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
      ],
      '/api/providers/readiness': {
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'ready',
          summary: '项目级证据运行时已就绪。',
          detail: null,
          action_label: null,
        },
      },
      '/api/projects/seed-reconciliation': {
        id: 'seed-reconciliation',
        name: '集团业财逐笔对账需求分析',
        scenario_type: 'reconciliation',
        summary: '默认 seed 项目。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: 'seed-reconciliation',
      },
      '/api/projects/seed-reconciliation/sources': [],
      '/api/projects/seed-reconciliation/messages': [],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [],
        pending_items: [],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/seed-reconciliation/readiness': {
        project_id: 'seed-reconciliation',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'ready',
          summary: '当前项目知识库可用于证据检索。',
          detail: 'Collection: seed-reconciliation; indexed chunks: 0',
          action_label: null,
        },
      },
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' });
    await user.click(screen.getByRole('link', { name: '项目列表' }));

    expect(await screen.findByRole('heading', { name: '客户需求转译台' })).toBeInTheDocument();
    expect(screen.getByText('选择一个项目进入工作台')).toBeInTheDocument();
  });

  it('opens a dialog when importing text source', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    installFetchMock({
      '/api/projects/seed-reconciliation': {
        id: 'seed-reconciliation',
        name: '集团业财逐笔对账需求分析',
        scenario_type: 'reconciliation',
        summary: '默认 seed 项目。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: 'seed-reconciliation',
      },
      '/api/projects/seed-reconciliation/sources': [],
      '/api/projects/seed-reconciliation/messages': [],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [],
        pending_items: [],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/seed-reconciliation/readiness': {
        project_id: 'seed-reconciliation',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'knowledge_base_missing',
          summary: '当前项目还没有初始化项目内知识库。',
          detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
          action_label: '初始化知识库',
        },
        knowledge_base: null,
      },
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    const user = userEvent.setup();

    render(<App />);

    await user.click(await screen.findByRole('button', { name: '导入文本资料' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '导入文本资料' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('例如：客户访谈纪要')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('粘贴纪要、需求原话或规则说明。')).toBeInTheDocument();
  });

  it('opens a dialog when importing a source url', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    installFetchMock({
      '/api/projects/seed-reconciliation': {
        id: 'seed-reconciliation',
        name: '集团业财逐笔对账需求分析',
        scenario_type: 'reconciliation',
        summary: '默认 seed 项目。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: 'seed-reconciliation',
      },
      '/api/projects/seed-reconciliation/sources': [],
      '/api/projects/seed-reconciliation/messages': [],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [],
        pending_items: [],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/seed-reconciliation/readiness': {
        project_id: 'seed-reconciliation',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'knowledge_base_missing',
          summary: '当前项目还没有初始化项目内知识库。',
          detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
          action_label: '初始化知识库',
        },
        knowledge_base: null,
      },
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    const user = userEvent.setup();

    render(<App />);

    await user.click(await screen.findByRole('button', { name: '导入网页链接' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '导入网页链接' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('例如：退款规则链接')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('粘贴网页地址，例如 https://docs.example.com/help/refund-policy')).toBeInTheDocument();
  });

  it('opens the project knowledge base dialog with the existing binding controls and updated wording', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    installFetchMock({
      '/api/projects/seed-reconciliation': {
        id: 'seed-reconciliation',
        name: '集团业财逐笔对账需求分析',
        scenario_type: 'reconciliation',
        summary: '默认 seed 项目。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: 'seed-reconciliation',
      },
      '/api/projects/seed-reconciliation/sources': [],
      '/api/projects/seed-reconciliation/messages': [],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [],
        pending_items: [],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/seed-reconciliation/readiness': {
        project_id: 'seed-reconciliation',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'knowledge_base_missing',
          summary: '当前项目还没有初始化项目内知识库。',
          detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
          action_label: '初始化知识库',
        },
        knowledge_base: null,
      },
      '/api/projects/seed-reconciliation/knowledge-base': {
        project_id: 'seed-reconciliation',
        knowledge_base: null,
        readiness: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'knowledge_base_missing',
          summary: '当前项目还没有初始化项目内知识库。',
          detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
          action_label: '初始化知识库',
        },
        source_count: 0,
        chunk_count: 0,
        indexed_chunk_count: 0,
      },
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: '运行状态' }));
    await user.click(screen.getByRole('button', { name: '项目知识库详情' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '项目知识库详情' })).toBeInTheDocument();
    expect(screen.getByText('当前项目还没有初始化项目知识库。')).toBeInTheDocument();
    expect(screen.getByText('初始化完成后，新导入资料会自动进入标准化、分块和索引流程。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '初始化项目知识库' })).toBeInTheDocument();
    expect(screen.queryByText('已登记的知识库')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '创建并绑定知识库' })).not.toBeInTheDocument();
  });

  it('can delete a source from the workbench', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    let deleted = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/sources/src-1' && method === 'DELETE') {
        deleted = true;
        return new Response(
          JSON.stringify({
            id: 'src-1',
            project_id: 'seed-reconciliation',
            name: '财务口径说明',
            deleted: true,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': deleted
          ? []
          : [
              {
                id: 'src-1',
                project_id: 'seed-reconciliation',
                name: '财务口径说明',
                source_kind: 'document',
                upload_kind: 'seed',
                storage_path: null,
                normalized_path: null,
                index_input_mode: null,
                normalize_status: 'parsed',
                normalize_summary: '解释业务字段到财务科目的映射口径。',
                index_status: 'pending',
                index_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
              },
            ],
        '/api/projects/seed-reconciliation/messages': [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'knowledge_base_missing',
            summary: '当前项目还没有初始化项目内知识库。',
            detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: '初始化知识库',
          },
          knowledge_base: null,
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: '删除 财务口径说明' }));

    await waitFor(() => {
      expect(screen.queryByText('财务口径说明')).not.toBeInTheDocument();
    });
  });

  it('reindexes a failed source from the workbench', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    let retried = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/sources/src-1/reindex' && method === 'POST') {
        retried = true;
        return new Response(
          JSON.stringify({
            id: 'src-1',
            project_id: 'seed-reconciliation',
            name: '财务口径说明',
            source_kind: 'document',
            upload_kind: 'file',
            storage_path: null,
            normalized_path: null,
            index_input_mode: null,
            normalize_status: 'parsed',
            normalize_summary: '解释业务字段到财务科目的映射口径。',
            index_status: 'indexed',
            index_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [
          {
            id: 'src-1',
            project_id: 'seed-reconciliation',
            name: '财务口径说明',
            source_kind: 'document',
            upload_kind: 'file',
            storage_path: null,
            normalized_path: null,
            index_input_mode: null,
            normalize_status: 'parsed',
            normalize_summary: '解释业务字段到财务科目的映射口径。',
            index_status: retried ? 'indexed' : 'index_failed',
            index_error: retried ? null : 'Evidence Runtime 调用失败：ConnectError',
            created_at: '2026-04-16T00:00:00+08:00',
          },
        ],
        '/api/projects/seed-reconciliation/messages': [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '当前项目知识库可用于证据检索。',
            detail: 'Collection: seed-reconciliation; indexed chunks: 1',
            action_label: null,
          },
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText('入库失败')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试入库 财务口径说明' }));

    await waitFor(() => {
      expect(retried).toBe(true);
      expect(screen.getByText('已入库')).toBeInTheDocument();
    });
  });

  it('uploads multiple files in a single request', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    const uploadedBatches: Array<{ names: string[]; uploadKind: string | null }> = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/sources' && method === 'POST') {
        const formData = init?.body as FormData;
        uploadedBatches.push({
          uploadKind: formData.get('upload_kind')?.toString() ?? null,
          names: formData
            .getAll('files')
            .map((entry) => (entry instanceof File ? entry.name : String(entry))),
        });
        return new Response(
          JSON.stringify([
            {
              id: 'src-batch-1',
              project_id: 'seed-reconciliation',
              name: '规则A.md',
              source_kind: 'document',
              upload_kind: 'file',
              storage_path: null,
              normalized_path: null,
              index_input_mode: null,
              normalize_status: 'parsed',
              normalize_summary: '规则A',
              index_status: 'pending',
              index_error: null,
              created_at: '2026-04-16T00:00:00+08:00',
            },
            {
              id: 'src-batch-2',
              project_id: 'seed-reconciliation',
              name: '规则B.md',
              source_kind: 'document',
              upload_kind: 'file',
              storage_path: null,
              normalized_path: null,
              index_input_mode: null,
              normalize_status: 'parsed',
              normalize_summary: '规则B',
              index_status: 'pending',
              index_error: null,
              created_at: '2026-04-16T00:00:00+08:00',
            },
          ]),
          { status: 201, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '当前项目知识库可用于证据检索。',
            detail: 'Collection: seed-reconciliation; indexed chunks: 0',
            action_label: null,
          },
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).not.toBeNull();

    const fileA = new File(['规则A'], '规则A.md', { type: 'text/markdown' });
    const fileB = new File(['规则B'], '规则B.md', { type: 'text/markdown' });

    await user.upload(fileInput!, [fileA, fileB]);

    await waitFor(() => {
      expect(uploadedBatches).toEqual([
        {
          uploadKind: 'file',
          names: ['规则A.md', '规则B.md'],
        },
      ]);
    });
  });

  it('sends on Enter and keeps Shift+Enter for newline in the composer', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });

    const chatRequests: string[] = [];
    const knowledgeBaseInitRequests: string[] = [];
    let knowledgeBaseReady = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        knowledgeBaseInitRequests.push(path);
        return new Response(
          JSON.stringify({
            id: 'kb-created-001',
            project_id: 'seed-reconciliation',
            provider: 'QDRANT_LLAMAINDEX',
            external_knowledge_base_id: 'seed-reconciliation',
            display_name: '集团业财逐笔对账需求分析',
            description: null,
            status: 'ready',
            status_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
            updated_at: '2026-04-16T00:00:00+08:00',
          }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      }

      if (path === '/api/projects/seed-reconciliation/chat/stream' && method === 'POST') {
        const body = JSON.parse(String(init?.body ?? '{}')) as { message?: string };
        chatRequests.push(body.message ?? '');
        return new Response(
          [
            'event: message_chunk',
            'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","text":"已收到。"}',
            '',
            'event: done',
            'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","stream_group_id":"stream-1"}',
            '',
          ].join('\n'),
          {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: seed-reconciliation; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-created-001',
                project_id: 'seed-reconciliation',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'seed-reconciliation',
                display_name: '集团业财逐笔对账需求分析',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
        },
        '/api/projects/seed-reconciliation/knowledge-base': {
          project_id: 'seed-reconciliation',
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-created-001',
                project_id: 'seed-reconciliation',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'seed-reconciliation',
                display_name: '集团业财逐笔对账需求分析',
                description: null,
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: seed-reconciliation; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByPlaceholderText('继续补充背景、确认范围，或让系统基于当前资料生成理解。');

    await user.type(composer, '第一行');
    await user.keyboard('{Shift>}{Enter}{/Shift}第二行');

    expect(composer).toHaveValue('第一行\n第二行');
    expect(chatRequests).toHaveLength(0);

    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(knowledgeBaseInitRequests).toEqual(['/api/projects/seed-reconciliation/knowledge-base/init']);
      expect(chatRequests).toEqual(['第一行\n第二行']);
    });
  });

  it('renders assistant chunks before the SSE stream finishes', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    const encoder = new TextEncoder();
    let chatCompleted = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/chat/stream' && method === 'POST') {
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                [
                  'event: assistant_status',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","phase":"evidence_query","label":"正在检索项目知识库证据与引用"}',
                  '',
                  '',
                  'event: message_chunk',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","text":"第一段"}',
                  '',
                  '',
                ].join('\n')
              )
            );

            setTimeout(() => {
              controller.enqueue(
                encoder.encode(
                  [
                    'event: message_chunk',
                    'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:01+08:00","text":"第二段"}',
                    '',
                    '',
                  ].join('\n')
                )
              );
            }, 120);

            setTimeout(() => {
              chatCompleted = true;
              controller.enqueue(
                encoder.encode(
                  [
                    'event: done',
                    'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:02+08:00","stream_group_id":"stream-1"}',
                    '',
                    '',
                  ].join('\n')
                )
              );
              controller.close();
            }, 180);
          },
        });

        return new Response(stream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': chatCompleted
          ? [
              {
                id: 'msg-assistant-final',
                role: 'assistant',
                content: '第一段第二段',
                source_refs: [],
                created_at: '2026-04-16T00:00:02+08:00',
                stream_group_id: 'stream-1',
              },
            ]
          : [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: chatCompleted
            ? [
                {
                  id: 'new-understanding-1',
                  title: '当前需求定义',
                  body: '先确认逐笔对账范围，再推进 MVP。',
                  status: 'active',
                  category: 'current_understanding',
                  updated_at: '2026-04-16T10:00:00+08:00',
                  source_ids: ['src-1'],
                },
              ]
            : [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '当前项目知识库可用于证据检索。',
            detail: 'Collection: seed-reconciliation; indexed chunks: 0',
            action_label: null,
          },
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByPlaceholderText('继续补充背景、确认范围，或让系统基于当前资料生成理解。');
    await user.type(composer, '请开始分析');
    await user.keyboard('{Enter}');

    expect(await screen.findByText('正在检索项目知识库证据与引用')).toBeInTheDocument();
    expect(await screen.findByText('第一段')).toBeInTheDocument();
    expect(screen.queryByText('第一段第二段')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('第一段第二段')).toBeInTheDocument();
    });
  });

  it('renders markdown formatting in assistant messages', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    let chatCompleted = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/chat/stream' && method === 'POST') {
        chatCompleted = true;
        return new Response(
          [
            'event: message_chunk',
            'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","text":"**重点结论**\\n\\n- 第一条"}',
            '',
            'event: done',
            'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:01+08:00","stream_group_id":"stream-1"}',
            '',
          ].join('\n'),
          {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': chatCompleted
          ? [
              {
                id: 'msg-md-1',
                role: 'assistant',
                content: '**重点结论**\n\n- 第一条',
                source_refs: [],
                created_at: '2026-04-16T00:00:01+08:00',
                stream_group_id: 'stream-1',
              },
            ]
          : [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '当前项目知识库可用于证据检索。',
            detail: 'Collection: seed-reconciliation; indexed chunks: 0',
            action_label: null,
          },
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByPlaceholderText('继续补充背景、确认范围，或让系统基于当前资料生成理解。');
    await user.type(composer, '请给我结论');
    await user.keyboard('{Enter}');

    expect(await screen.findByText('第一条')).toBeInTheDocument();

    const strong = document.querySelector('.markdown-body strong');
    expect(strong?.textContent).toBe('重点结论');
  });

  it('shows the ready project knowledge base details from the runtime entrypoint', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    let knowledgeBaseReady = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        return new Response(
          JSON.stringify({
            id: 'kb-created-001',
            project_id: 'seed-reconciliation',
            provider: 'QDRANT_LLAMAINDEX',
            external_knowledge_base_id: 'seed-reconciliation',
            display_name: '集团业财逐笔对账需求分析',
            description: '项目知识库',
            status: 'ready',
            status_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
            updated_at: '2026-04-16T00:00:00+08:00',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/knowledge-base': {
          project_id: 'seed-reconciliation',
          knowledge_base: knowledgeBaseReady
            ? {
                id: 'kb-created-001',
                project_id: 'seed-reconciliation',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'seed-reconciliation',
                display_name: '集团业财逐笔对账需求分析',
                description: '项目知识库',
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              }
            : null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: knowledgeBaseReady ? 'ready' : 'knowledge_base_missing',
            summary: knowledgeBaseReady ? '当前项目知识库可用于证据检索。' : '当前项目还没有初始化项目内知识库。',
            detail: knowledgeBaseReady ? 'Collection: seed-reconciliation; indexed chunks: 0' : '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: knowledgeBaseReady ? null : '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/seed-reconciliation/artifacts': [],
        '/api/projects/seed-reconciliation/readiness': knowledgeBaseReady
          ? {
              project_id: 'seed-reconciliation',
              claude: {
                provider: 'CLAUDE_AGENT_SDK',
                status: 'ready',
                summary: 'Claude Agent SDK 已就绪。',
                detail: null,
                action_label: null,
              },
              evidence: {
                provider: 'QDRANT_LLAMAINDEX',
                status: 'ready',
                summary: '当前项目知识库可用于证据检索。',
                detail: 'Collection: seed-reconciliation; indexed chunks: 0',
                action_label: null,
              },
              knowledge_base: {
                id: 'kb-created-001',
                project_id: 'seed-reconciliation',
                provider: 'QDRANT_LLAMAINDEX',
                external_knowledge_base_id: 'seed-reconciliation',
                display_name: '集团业财逐笔对账需求分析',
                description: '项目知识库',
                status: 'ready',
                status_error: null,
                created_at: '2026-04-16T00:00:00+08:00',
                updated_at: '2026-04-16T00:00:00+08:00',
              },
            }
          : {
              project_id: 'seed-reconciliation',
              claude: {
                provider: 'CLAUDE_AGENT_SDK',
                status: 'ready',
                summary: 'Claude Agent SDK 已就绪。',
                detail: null,
                action_label: null,
              },
              evidence: {
                provider: 'QDRANT_LLAMAINDEX',
                status: 'knowledge_base_missing',
                summary: '当前项目还没有初始化项目内知识库。',
                detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
                action_label: '初始化知识库',
              },
              knowledge_base: null,
            },
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Evidence: 已就绪')).toBeInTheDocument();
    });

    await user.click(await screen.findByRole('button', { name: '运行状态' }));
    await user.click(screen.getByRole('button', { name: '项目知识库详情' }));
    expect(screen.getByRole('heading', { name: '项目知识库详情' })).toBeInTheDocument();
    expect(screen.getByText('当前项目知识库已初始化并可用于证据检索。')).toBeInTheDocument();
    expect(screen.getByText('Collection ID')).toBeInTheDocument();
    expect(screen.getByText('seed-reconciliation')).toBeInTheDocument();
    expect(screen.getByText('已索引分块')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '初始化项目知识库' })).not.toBeInTheDocument();
    expect(screen.queryByText('已登记的知识库')).not.toBeInTheDocument();
  });

  it('does not send chat when knowledge base initialization fails', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    let knowledgeBaseInitCalls = 0;
    let chatStreamCalls = 0;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/knowledge-base/init' && method === 'POST') {
        knowledgeBaseInitCalls += 1;
        return new Response('knowledge base init failed', { status: 500 });
      }

      if (path === '/api/projects/seed-reconciliation/chat/stream' && method === 'POST') {
        chatStreamCalls += 1;
        return new Response('should not be called', { status: 500 });
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/knowledge-base': {
          project_id: 'seed-reconciliation',
          knowledge_base: null,
          readiness: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'knowledge_base_missing',
            summary: '当前项目还没有初始化项目内知识库。',
            detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: '初始化知识库',
          },
          source_count: 0,
          chunk_count: 0,
          indexed_chunk_count: 0,
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'knowledge_base_missing',
            summary: '当前项目还没有初始化项目内知识库。',
            detail: '需要先创建项目级 collection，并为 source 建立本地向量索引。',
            action_label: '初始化知识库',
          },
          knowledge_base: null,
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByPlaceholderText('继续补充背景、确认范围，或让系统基于当前资料生成理解。');
    await user.type(composer, '请给我结论');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(knowledgeBaseInitCalls).toBeGreaterThan(0);
    });
    expect(chatStreamCalls).toBe(0);
    expect((await screen.findAllByText('项目知识库自动初始化失败')).length).toBeGreaterThan(0);
  });

  it('sanitizes dirty state text and only shows the latest artifact per type in the sidebar', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    installFetchMock({
      '/api/projects/seed-reconciliation': {
        id: 'seed-reconciliation',
        name: '集团业财逐笔对账需求分析',
        scenario_type: 'reconciliation',
        summary: '默认 seed 项目。',
        status: 'active',
        created_at: '2026-04-16T00:00:00+08:00',
        updated_at: '2026-04-16T00:00:00+08:00',
        seed_key: 'seed-reconciliation',
      },
      '/api/projects/seed-reconciliation/sources': [],
      '/api/projects/seed-reconciliation/messages': [],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [
          {
            id: 'understanding-1',
            title: '项目核心问题',
            body: '项目核心问题：业务字段与财务科目映射口径不一致；content: 项目核心问题：业务字段与财务科目映射口径不一致',
            status: 'active',
            category: 'current_understanding',
            updated_at: '2026-04-16T10:00:00+08:00',
            source_ids: ['src-1'],
          },
        ],
        pending_items: [
          {
            id: 'pending-1',
            title: '一期输出物边界',
            body: '结构化需求摘要还是方案雏形？；content: 一期输出物边界：结构化需求摘要还是方案雏形？；impact: 影响验收标准',
            status: 'active',
            category: 'pending_items',
            updated_at: '2026-04-16T10:05:00+08:00',
            source_ids: [],
          },
        ],
        confirmed_items: [],
        conflict_items: [],
        mvp_items: [],
        versions: [],
        artifacts: [],
      },
      '/api/projects/seed-reconciliation/readiness': {
        project_id: 'seed-reconciliation',
        claude: {
          provider: 'CLAUDE_AGENT_SDK',
          status: 'ready',
          summary: 'Claude Agent SDK 已就绪。',
          detail: null,
          action_label: null,
        },
        evidence: {
          provider: 'QDRANT_LLAMAINDEX',
          status: 'ready',
          summary: '当前项目知识库可用于证据检索。',
          detail: 'Collection: seed-reconciliation; indexed chunks: 0',
          action_label: null,
        },
      },
      '/api/projects/seed-reconciliation/artifacts': [
        {
          id: 'artifact-page-new',
          project_id: 'seed-reconciliation',
          artifact_type: 'page_solution',
          title: '页面方案 v2',
          summary: '最新页面方案',
          status: 'generated',
          content_format: 'html',
          storage_path: '/tmp/page-v2.html',
          preview_url: '/api/projects/seed-reconciliation/artifacts/artifact-page-new/preview',
          body: null,
          updated_at: '2026-04-16T10:10:00+08:00',
        },
        {
          id: 'artifact-page-old',
          project_id: 'seed-reconciliation',
          artifact_type: 'page_solution',
          title: '页面方案 v1',
          summary: '旧页面方案',
          status: 'generated',
          content_format: 'html',
          storage_path: '/tmp/page-v1.html',
          preview_url: '/api/projects/seed-reconciliation/artifacts/artifact-page-old/preview',
          body: null,
          updated_at: '2026-04-16T09:00:00+08:00',
        },
        {
          id: 'artifact-flow-new',
          project_id: 'seed-reconciliation',
          artifact_type: 'interaction_flow',
          title: '交互稿 v2',
          summary: '最新交互稿',
          status: 'generated',
          content_format: 'html',
          storage_path: '/tmp/flow-v2.html',
          preview_url: '/api/projects/seed-reconciliation/artifacts/artifact-flow-new/preview',
          body: null,
          updated_at: '2026-04-16T10:11:00+08:00',
        },
        {
          id: 'artifact-document-new',
          project_id: 'seed-reconciliation',
          artifact_type: 'document',
          title: '文档稿 v2',
          summary: '最新文档稿',
          status: 'generated',
          content_format: 'markdown',
          storage_path: null,
          preview_url: null,
          body: '# 文档稿',
          updated_at: '2026-04-16T10:12:00+08:00',
        },
      ],
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' })).toBeInTheDocument();
    expect(screen.getByText('业务字段与财务科目映射口径不一致')).toBeInTheDocument();
    expect(screen.queryByText(/content:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/impact:/)).not.toBeInTheDocument();

    expect(screen.getByRole('button', { name: /页面方案 v2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /交互稿 v2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /文档稿 v2/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /页面方案 v1/ })).not.toBeInTheDocument();
  });

  it('marks freshly patched insights as new in the sidebar', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    const encoder = new TextEncoder();
    let chatCompleted = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/chat/stream' && method === 'POST') {
        chatCompleted = true;
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  [
                    'event: current_understanding_patch',
                    'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T10:00:00+08:00","items":[{"id":"new-understanding-1","title":"当前需求定义","body":"先确认逐笔对账范围，再推进 MVP。","status":"active","category":"current_understanding","updated_at":"2026-04-16T10:00:00+08:00","source_ids":["src-1"]}]}',
                    '',
                    'event: done',
                    'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T10:00:01+08:00","stream_group_id":"stream-1"}',
                    '',
                  ].join('\n')
                )
              );
              controller.close();
            },
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          }
        );
      }

      const routes: Record<string, JsonResponse> = {
        '/api/projects/seed-reconciliation': {
          id: 'seed-reconciliation',
          name: '集团业财逐笔对账需求分析',
          scenario_type: 'reconciliation',
          summary: '默认 seed 项目。',
          status: 'active',
          created_at: '2026-04-16T00:00:00+08:00',
          updated_at: '2026-04-16T00:00:00+08:00',
          seed_key: 'seed-reconciliation',
        },
        '/api/projects/seed-reconciliation/sources': [],
        '/api/projects/seed-reconciliation/messages': chatCompleted
          ? [
              {
                id: 'msg-user-1',
                role: 'user',
                content: '请继续分析',
                source_refs: [],
                created_at: '2026-04-16T10:00:00+08:00',
                stream_group_id: 'stream-1',
              },
            ]
          : [],
        '/api/projects/seed-reconciliation/state': {
          current_understanding: chatCompleted
            ? [
                {
                  id: 'new-understanding-1',
                  title: '当前需求定义',
                  body: '先确认逐笔对账范围，再推进 MVP。',
                  status: 'active',
                  category: 'current_understanding',
                  updated_at: '2026-04-16T10:00:00+08:00',
                  source_ids: ['src-1'],
                },
              ]
            : [],
          pending_items: [],
          confirmed_items: [],
          conflict_items: [],
          mvp_items: [],
          versions: [],
          artifacts: [],
        },
        '/api/projects/seed-reconciliation/readiness': {
          project_id: 'seed-reconciliation',
          claude: {
            provider: 'CLAUDE_AGENT_SDK',
            status: 'ready',
            summary: 'Claude Agent SDK 已就绪。',
            detail: null,
            action_label: null,
          },
          evidence: {
            provider: 'QDRANT_LLAMAINDEX',
            status: 'ready',
            summary: '当前项目知识库可用于证据检索。',
            detail: 'Collection: seed-reconciliation; indexed chunks: 0',
            action_label: null,
          },
        },
        '/api/projects/seed-reconciliation/artifacts': [],
      };

      const payload = routes[path];
      if (!payload) {
        return new Response(`Unhandled request for ${method} ${path}`, { status: 404 });
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const user = userEvent.setup();
    render(<App />);

    const composer = await screen.findByPlaceholderText('继续补充背景、确认范围，或让系统基于当前资料生成理解。');
    await user.type(composer, '请继续分析');
    await user.keyboard('{Enter}');

    expect(await screen.findByText('当前需求定义')).toBeInTheDocument();
    expect(await screen.findByText('本轮新增')).toBeInTheDocument();
  });
});
