import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import App from './App';

type JsonResponse = Record<string, unknown> | Array<unknown>;
type RoutePayload = JsonResponse | (() => JsonResponse);

function installFetchMock(routes: Record<string, RoutePayload>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const path = new URL(url, 'http://localhost').pathname;
    const route = routes[path];
    const payload = typeof route === 'function' ? route() : route;

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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'auth_required',
          summary: '项目知识库 还没有在项目内完成认证。',
          detail: '需要先认证',
          action_label: '完成项目内登录',
        },
      },
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '客户需求转译台' })).toBeInTheDocument();
    expect(await screen.findByText('集团业财逐笔对账')).toBeInTheDocument();
    expect(screen.getByText('选择一个项目进入工作台')).toBeInTheDocument();
    expect(screen.getByText('Provider Readiness')).toBeInTheDocument();
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
            knowledge_base: {
              id: 'nb-created-001',
              name: '渠道对账需求分析',
              url: 'https://qdrant.local/knowledge-base/nb-created-001',
              description: '',
              topics: [],
              use_count: 0,
              last_used: null,
            },
            binding: {
              project_id: 'project-created-001',
              id: 'nb-created-001',
              provider: 'QDRANT_LLAMA_INDEX',
              status: 'bound',
              updated_at: null,
              status_error: 'https://qdrant.local/knowledge-base/nb-created-001',
            },
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库 已就绪。',
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: knowledgeBaseReady ? 'ready' : 'ready',
            summary: knowledgeBaseReady ? '项目知识库已就绪。' : '项目知识库可初始化。',
            detail: knowledgeBaseReady ? 'Knowledge Base ID: nb-created-001' : '需要初始化',
            action_label: knowledgeBaseReady ? null : '初始化项目 knowledgeBase',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                project_id: 'project-created-001',
                id: 'nb-created-001',
                provider: 'QDRANT_LLAMA_INDEX',
                status: 'bound',
                updated_at: null,
                status_error: 'https://qdrant.local/knowledge-base/nb-created-001',
              }
            : null,
        },
        '/api/projects/project-created-001/knowledge-base': [],
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
    expect(await screen.findByText('项目知识库: ready')).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/projects',
      expect.objectContaining({
        method: 'POST',
      })
    );
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/projects/project-created-001/knowledge-base/init',
      expect.objectContaining({
        method: 'POST',
      })
    );
  });

  it('auto-binds knowledgeBase when entering an existing unbound project workbench', async () => {
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
            knowledge_base: {
              id: 'nb-legacy-001',
              name: '历史项目 Knowledge Base',
              url: 'https://qdrant.local/knowledge-base/nb-legacy-001',
              description: '',
              topics: [],
              use_count: 0,
              last_used: null,
            },
            binding: {
              project_id: 'project-legacy-001',
              id: 'nb-legacy-001',
              provider: 'QDRANT_LLAMA_INDEX',
              status: 'bound',
              updated_at: null,
              status_error: 'https://qdrant.local/knowledge-base/nb-legacy-001',
            },
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
          summary: '一个之前创建但还没初始化 knowledgeBase 的项目。',
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: knowledgeBaseReady ? 'ready' : 'ready',
            summary: knowledgeBaseReady ? '项目知识库已就绪。' : '项目知识库可初始化。',
            detail: knowledgeBaseReady ? 'Knowledge Base ID: nb-legacy-001' : '需要初始化',
            action_label: knowledgeBaseReady ? null : '初始化项目 knowledgeBase',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                project_id: 'project-legacy-001',
                id: 'nb-legacy-001',
                provider: 'QDRANT_LLAMA_INDEX',
                status: 'bound',
                updated_at: null,
                status_error: 'https://qdrant.local/knowledge-base/nb-legacy-001',
              }
            : null,
        },
        '/api/projects/project-legacy-001/knowledge-base': [],
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

    expect(await screen.findByText('项目知识库: ready')).toBeInTheDocument();
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
          status: 'pending',
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库已就绪。',
          detail: 'Knowledge Base ID: nb-seed-001',
          action_label: null,
        },
        knowledge_base: {
          project_id: 'seed-reconciliation',
          id: 'nb-seed-001',
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'bound',
          updated_at: null,
          status_error: 'https://qdrant.local/knowledge-base/nb-seed-001',
        },
      },
      '/api/projects/seed-reconciliation/knowledge-base': [
        {
          id: 'nb-1',
          name: '集团业财逐笔对账 Knowledge Base',
          url: 'https://qdrant.local/knowledge-base/seed123',
          description: '默认演示 knowledgeBase',
          topics: ['业财对账', '需求分析'],
          use_count: 2,
          last_used: null,
        },
      ],
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' })).toBeInTheDocument();
    expect(await screen.findByText('项目知识库')).toBeInTheDocument();
    expect((await screen.findAllByText('财务口径说明')).length).toBeGreaterThan(0);
    expect(await screen.findByText('我先把逐笔对账的真实矛盾拆开。')).toBeInTheDocument();
    expect(await screen.findByText('本轮更新')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: '展开 当前需求定义' }));
    expect(await screen.findByText('核心矛盾')).toBeInTheDocument();
    expect(await screen.findByText('当前重点')).toBeInTheDocument();
    expect((await screen.findAllByText('业务理解')).length).toBeGreaterThan(0);
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
      expect(globalThis.fetch).toHaveBeenCalledTimes(6);
    });
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库 已就绪。',
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库已就绪。',
          detail: 'Knowledge Base ID: nb-seed-001',
          action_label: null,
        },
        knowledge_base: {
          project_id: 'seed-reconciliation',
          id: 'nb-seed-001',
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'bound',
          updated_at: null,
          status_error: 'https://qdrant.local/knowledge-base/nb-seed-001',
        },
      },
      '/api/projects/seed-reconciliation/knowledge-base': [],
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库可初始化。',
          detail: '需要先初始化',
          action_label: '初始化项目知识库',
        },
        knowledge_base: null,
      },
      '/api/projects/seed-reconciliation/knowledge-base': [],
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

  it('shows project knowledgeBase readiness inside the runtime dialog', async () => {
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库可初始化。',
          detail: '需要先初始化',
          action_label: '初始化项目知识库',
        },
        knowledge_base: null,
      },
      '/api/projects/seed-reconciliation/knowledge-base': [
        {
          id: 'nb-1',
          name: '集团业财逐笔对账 Knowledge Base',
          url: 'https://qdrant.local/knowledge-base/seed123',
          description: '默认演示 knowledgeBase',
          topics: ['业财对账', '需求分析'],
          use_count: 2,
          last_used: null,
        },
      ],
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: '运行状态' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getAllByText('项目知识库').length).toBeGreaterThan(0);
  });

  it('renders audio source processing states and refreshes while source work is active', async () => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });

    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    let sourceRequestCount = 0;
    const setIntervalSpy = vi.spyOn(window, 'setInterval');

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
      '/api/projects/seed-reconciliation/sources': () => {
        sourceRequestCount += 1;

        if (sourceRequestCount === 1) {
          return [
            {
              id: 'src-audio-1',
              project_id: 'seed-reconciliation',
              name: '客户访谈录音.wav',
              source_kind: 'audio',
              upload_kind: 'file',
              storage_path: '/tmp/audio.wav',
              normalized_path: null,
              index_input_mode: 'audio_transcript',
              normalize_status: 'processing',
              normalize_summary: '正在提取录音里的业务字段和财务口径。',
              index_status: 'normalization_pending',
              index_error: null,
              created_at: '2026-04-16T00:00:00+08:00',
            },
          ];
        }

        return [
          {
            id: 'src-audio-1',
            project_id: 'seed-reconciliation',
            name: '客户访谈录音.wav',
            source_kind: 'audio',
            upload_kind: 'file',
            storage_path: '/tmp/audio.wav',
            normalized_path: '/tmp/audio.md',
            index_input_mode: 'audio_transcript',
            normalize_status: 'parsed',
            normalize_summary: '录音已转写：先统一订单口径，再对齐财务科目映射。',
            index_status: 'indexing',
            index_error: null,
            created_at: '2026-04-16T00:00:00+08:00',
          },
        ];
      },
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库已就绪。',
          detail: 'Knowledge Base ID: nb-audio-001',
          action_label: null,
        },
        knowledge_base: {
          project_id: 'seed-reconciliation',
          id: 'nb-audio-001',
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'bound',
          updated_at: null,
          status_error: 'https://qdrant.local/knowledge-base/nb-audio-001',
        },
      },
      '/api/projects/seed-reconciliation/knowledge-base': [],
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' })).toBeInTheDocument();
    expect(await screen.findByText('标准化：标准化中')).toBeInTheDocument();
    expect(screen.getByText('入库：待标准化')).toBeInTheDocument();
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 3000);

    await waitFor(() => {
      expect(screen.getByText('标准化：已标准化')).toBeInTheDocument();
    }, { timeout: 4000 });
    expect(screen.getByText('入库：入库中')).toBeInTheDocument();
    expect(screen.getByText('录音已转写：先统一订单口径，再对齐财务科目映射。')).toBeInTheDocument();
    expect(sourceRequestCount).toBeGreaterThanOrEqual(2);
  });

  it('shows audio transcript previews and runtime cards for Qiniu and Aliyun providers', async () => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
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
          id: 'src-audio-2',
          project_id: 'seed-reconciliation',
          name: '门店复盘录音.mp3',
          source_kind: 'audio',
          upload_kind: 'file',
          storage_path: '/tmp/store-call.mp3',
          normalized_path: '/tmp/store-call.md',
          index_input_mode: 'audio_transcript',
          normalize_status: 'parsed',
          normalize_summary: '音频转写摘要：退款口径和收入确认口径都需要补一轮澄清。',
          index_status: 'indexed',
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库已就绪。',
          detail: 'Knowledge Base ID: nb-audio-ready',
          action_label: null,
        },
        object_storage: {
          provider: 'QINIU_KODO',
          status: 'ready',
          summary: '七牛对象存储已就绪。',
          detail: 'Bucket: requirement-workbench-demo',
          action_label: null,
        },
        audio_transcription: {
          provider: 'ALIYUN_ASR',
          status: 'ready',
          summary: '阿里云音频转写已就绪。',
          detail: 'AppKey: demo-audio-app',
          action_label: null,
        },
        knowledge_base: {
          project_id: 'seed-reconciliation',
          id: 'nb-audio-ready',
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'bound',
          updated_at: null,
          status_error: 'https://qdrant.local/knowledge-base/nb-audio-ready',
        },
      },
      '/api/projects/seed-reconciliation/knowledge-base': [],
      '/api/projects/seed-reconciliation/artifacts': [],
    });

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText('标准化：已标准化')).toBeInTheDocument();
    expect(screen.getByText('入库：已入库')).toBeInTheDocument();
    expect(screen.getByText('音频转写摘要：退款口径和收入确认口径都需要补一轮澄清。')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '运行状态' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('七牛对象存储')).toBeInTheDocument();
    expect(within(dialog).getByText('七牛对象存储已就绪。')).toBeInTheDocument();
    expect(within(dialog).getByText('阿里云音频转写')).toBeInTheDocument();
    expect(within(dialog).getByText('阿里云音频转写已就绪。')).toBeInTheDocument();
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
                status: 'pending',
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库可初始化。',
            detail: '需要先初始化',
            action_label: '初始化项目知识库',
          },
          knowledge_base: null,
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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

  it('retries syncing a failed source from the workbench', async () => {
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
            status: 'synced',
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
            index_error: retried ? null : '项目知识库 调用失败：ConnectError',
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-seed-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-seed-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-seed-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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

    expect(await screen.findByText('入库：入库失败')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重建索引 财务口径说明' }));

    await waitFor(() => {
      expect(retried).toBe(true);
      expect(screen.getByText('入库：已入库')).toBeInTheDocument();
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
              status: 'pending_sync',
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
              status: 'pending_sync',
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-batch-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-batch-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-batch-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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
    const initRequests: string[] = [];
    let knowledgeBaseReady = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      const method = init?.method ?? 'GET';

      if (path === '/api/projects/seed-reconciliation/knowledge-base/init' && method === 'POST') {
        knowledgeBaseReady = true;
        initRequests.push(path);
        return new Response(
          JSON.stringify({
            knowledge_base: {
              id: 'nb-created-001',
              name: '集团业财逐笔对账需求分析',
              url: 'https://qdrant.local/knowledge-base/nb-created-001',
              description: '',
              topics: [],
              use_count: 0,
              last_used: null,
            },
            binding: {
              project_id: 'seed-reconciliation',
              id: 'nb-created-001',
              provider: 'QDRANT_LLAMA_INDEX',
              status: 'bound',
              updated_at: null,
              status_error: 'https://qdrant.local/knowledge-base/nb-created-001',
            },
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: knowledgeBaseReady ? 'ready' : 'ready',
            summary: knowledgeBaseReady ? '项目知识库已就绪。' : '项目知识库可初始化。',
            detail: knowledgeBaseReady ? 'Knowledge Base ID: nb-created-001' : '需要初始化',
            action_label: knowledgeBaseReady ? null : '初始化项目 knowledgeBase',
          },
          knowledge_base: knowledgeBaseReady
            ? {
                project_id: 'seed-reconciliation',
                id: 'nb-created-001',
                provider: 'QDRANT_LLAMA_INDEX',
                status: 'bound',
                updated_at: null,
                status_error: 'https://qdrant.local/knowledge-base/nb-created-001',
              }
            : null,
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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
      expect(initRequests).toEqual(['/api/projects/seed-reconciliation/knowledge-base/init']);
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
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","phase":"evidence_query","label":"正在读取 项目知识库 证据与引用"}',
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
            }, 30);

            setTimeout(() => {
              controller.enqueue(
                encoder.encode(
                  [
                    'event: message_chunk',
                    'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:01+08:00","text":"第一段第二段","replace":true}',
                    '',
                    '',
                  ].join('\n')
                )
              );
            }, 45);

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
            }, 80);
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-stream-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-stream-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-stream-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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

    expect(await screen.findByText('第一段')).toBeInTheDocument();
    expect(screen.queryByText('第一段第二段')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('第一段第二段')).toBeInTheDocument();
    });
  });

  it('does not show agent_started as a duplicated system action chip', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    const encoder = new TextEncoder();

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
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","phase":"agent_started","label":"已接收问题，正在启动分析"}',
                  '',
                  '',
                  'event: done',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:02+08:00","stream_group_id":"stream-1"}',
                  '',
                  '',
                ].join('\n')
              )
            );
            controller.close();
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-stream-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-stream-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-stream-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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

    await waitFor(() => {
      expect(screen.queryByText('系统行动')).not.toBeInTheDocument();
    });
  });

  it('renders assistant action events for status, state, artifact and version patches', async () => {
    window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');

    const encoder = new TextEncoder();

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
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:00+08:00","phase":"evidence_query","label":"正在读取 项目知识库 证据与引用"}',
                  '',
                  'event: message_chunk',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:01+08:00","text":"先整理一版。"}',
                  '',
                  'event: current_understanding_patch',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:02+08:00","items":[{"id":"cu-1","title":"当前理解","body":"先确认对账范围。","status":"active","category":"current_understanding","updated_at":"2026-04-16T00:00:02+08:00","source_ids":[]}]}',
                  '',
                  'event: artifact_patch',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:03+08:00","items":[{"id":"artifact-1","project_id":"seed-reconciliation","artifact_type":"interaction_flow","title":"交互稿 v1","summary":"流程草案","status":"generated","content_format":"html","storage_path":null,"preview_url":null,"body":null,"updated_at":"2026-04-16T00:00:03+08:00"}]}',
                  '',
                  'event: version_patch',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:04+08:00","items":[{"id":"version-1","title":"artifact_generated","body":"生成交互稿","status":"active","category":"versions","updated_at":"2026-04-16T00:00:04+08:00","source_ids":[]}]}',
                  '',
                  'event: done',
                  'data: {"project_id":"seed-reconciliation","created_at":"2026-04-16T00:00:05+08:00","stream_group_id":"stream-action-1"}',
                  '',
                ].join('\n')
              )
            );
            controller.close();
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-action-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-action-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-action-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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
    await user.type(composer, '请整理成交互稿');
    await user.keyboard('{Enter}');

    expect(await screen.findByText('系统行动')).toBeInTheDocument();
    expect(await screen.findByText('先整理一版。')).toBeInTheDocument();
    expect(await screen.findByText('正在读取 项目知识库 证据与引用')).toBeInTheDocument();
    expect(await screen.findByText('已写入当前理解（1）')).toBeInTheDocument();
    expect(await screen.findByText('已生成交付物：交互稿（HTML 交互原型）')).toBeInTheDocument();
    expect(await screen.findByText('已生成版本快照（1）')).toBeInTheDocument();
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-md-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-md-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-md-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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

  it('can create and bind a project knowledgeBase from the binding dialog', async () => {
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
            knowledge_base: {
              id: 'nb-created-001',
              name: '集团业财逐笔对账需求分析',
              url: 'https://qdrant.local/knowledge-base/nb-created-001',
              description: '项目专属 knowledgeBase',
              topics: ['reconciliation', '需求分析', 'project-bound'],
              use_count: 0,
              last_used: null,
            },
            binding: {
              project_id: 'seed-reconciliation',
              id: 'nb-created-001',
              provider: 'QDRANT_LLAMA_INDEX',
              status: 'bound',
              updated_at: null,
              status_error: 'https://qdrant.local/knowledge-base/nb-created-001',
            },
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
        '/api/projects/seed-reconciliation/knowledge-base': knowledgeBaseReady
          ? [
              {
                id: 'nb-created-001',
                name: '集团业财逐笔对账需求分析',
                url: 'https://qdrant.local/knowledge-base/nb-created-001',
                description: '项目专属 knowledgeBase',
                topics: ['reconciliation', '需求分析', 'project-bound'],
                use_count: 0,
                last_used: null,
              },
            ]
          : [],
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
                provider: 'QDRANT_LLAMA_INDEX',
                status: 'ready',
                summary: '项目知识库已就绪。',
                detail: 'Knowledge Base ID: nb-created-001',
                action_label: null,
              },
              knowledge_base: {
                project_id: 'seed-reconciliation',
                id: 'nb-created-001',
                provider: 'QDRANT_LLAMA_INDEX',
                status: 'bound',
                updated_at: null,
                status_error: 'https://qdrant.local/knowledge-base/nb-created-001',
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
                provider: 'QDRANT_LLAMA_INDEX',
                status: 'ready',
                summary: '项目知识库可初始化。',
                detail: '需要先初始化',
                action_label: '初始化项目知识库',
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

    await user.click(await screen.findByRole('button', { name: '运行状态' }));
    await waitFor(() => {
      expect(screen.getByText('项目知识库: ready')).toBeInTheDocument();
    });

    expect(await screen.findByText('项目知识库已就绪。')).toBeInTheDocument();
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库已就绪。',
          detail: 'Knowledge Base ID: nb-ready-001',
          action_label: null,
        },
        knowledge_base: {
          project_id: 'seed-reconciliation',
          id: 'nb-ready-001',
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'bound',
          updated_at: null,
          status_error: 'https://qdrant.local/knowledge-base/nb-ready-001',
        },
      },
      '/api/projects/seed-reconciliation/knowledge-base': [],
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

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByRole('heading', { name: '集团业财逐笔对账需求分析' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '展开 当前需求定义' }));
    expect(screen.getByText('业务字段与财务科目映射口径不一致')).toBeInTheDocument();
    expect(screen.queryByText(/content:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/impact:/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '展开 交付物' }));
    expect(screen.getAllByText('页面方案 v2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('交互稿 v2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('文档稿 v2').length).toBeGreaterThan(0);
    expect(screen.queryByText('页面方案 v1')).not.toBeInTheDocument();
    expect(screen.getAllByText('页面方案').length).toBeGreaterThan(0);
    expect(screen.getAllByText('HTML 页面原型').length).toBeGreaterThan(0);
    expect(screen.getAllByText('已生成').length).toBeGreaterThan(0);
    expect(screen.queryByText('page_solution')).not.toBeInTheDocument();
    expect(screen.queryByText('interaction_flow')).not.toBeInTheDocument();
    expect(screen.queryByText('document')).not.toBeInTheDocument();
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
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'ready',
            summary: '项目知识库已就绪。',
            detail: 'Knowledge Base ID: nb-ready-001',
            action_label: null,
          },
          knowledge_base: {
            project_id: 'seed-reconciliation',
            id: 'nb-ready-001',
            provider: 'QDRANT_LLAMA_INDEX',
            status: 'bound',
            updated_at: null,
            status_error: 'https://qdrant.local/knowledge-base/nb-ready-001',
          },
        },
        '/api/projects/seed-reconciliation/knowledge-base': [],
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

    expect((await screen.findAllByText('当前需求定义')).length).toBeGreaterThan(0);
    expect(await screen.findByText('本轮更新')).toBeInTheDocument();
  });

  it('shows stage focus, revisiting hints, and opens state drawers from the overview', async () => {
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
      '/api/projects/seed-reconciliation/messages': [
        {
          id: 'msg-assistant-1',
          role: 'assistant',
          content: '我先确认逐笔对账范围，再把当前理解写入沉淀。',
          source_refs: [],
          created_at: '2026-04-16T10:00:00+08:00',
          stream_group_id: null,
        },
      ],
      '/api/projects/seed-reconciliation/state': {
        current_understanding: [
          {
            id: 'understanding-1',
            title: '当前需求定义',
            body: '一期围绕业财逐笔对账分析推进。',
            status: 'active',
            category: 'current_understanding',
            updated_at: '2026-04-16T10:00:00+08:00',
            source_ids: ['src-1'],
          },
        ],
        pending_items: [],
        confirmed_items: [
          {
            id: 'confirmed-1',
            title: '对账粒度',
            body: '一期按逐笔对账推进。',
            status: 'confirmed',
            category: 'confirmed_items',
            updated_at: '2026-04-16T10:05:00+08:00',
            source_ids: ['src-1'],
          },
        ],
        conflict_items: [
          {
            id: 'conflict-1',
            title: '退款口径冲突',
            body: '退款与冲销在财务侧挂接口径不一致。',
            status: 'active',
            category: 'conflict_items',
            updated_at: '2026-04-16T10:10:00+08:00',
            source_ids: ['src-2'],
          },
        ],
        mvp_items: [
          {
            id: 'mvp-1',
            title: 'MVP 结论',
            body: '先做差异识别与人工确认闭环。',
            status: 'active',
            category: 'mvp_items',
            updated_at: '2026-04-16T10:12:00+08:00',
            source_ids: ['src-1'],
          },
        ],
        versions: [
          {
            id: 'version-1',
            title: '需求收敛快照',
            body: '已确认逐笔对账是主线。',
            status: 'snapshot',
            category: 'versions',
            updated_at: '2026-04-16T10:15:00+08:00',
            source_ids: [],
          },
        ],
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
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'ready',
          summary: '项目知识库已就绪。',
          detail: 'Knowledge Base ID: nb-ready-001',
          action_label: null,
        },
        knowledge_base: {
          project_id: 'seed-reconciliation',
          id: 'nb-ready-001',
          provider: 'QDRANT_LLAMA_INDEX',
          status: 'bound',
          updated_at: null,
          status_error: 'https://qdrant.local/knowledge-base/nb-ready-001',
        },
      },
      '/api/projects/seed-reconciliation/knowledge-base': [],
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
          updated_at: '2026-04-16T10:20:00+08:00',
        },
      ],
    });

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText('当前重点')).toBeInTheDocument();
    expect((await screen.findAllByText('方案定义')).length).toBeGreaterThan(0);
    expect(screen.getByText('补充中')).toBeInTheDocument();
    expect(screen.getByText('需求收敛')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '关键待确认' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '风险与冲突' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '展开 风险与冲突' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '风险与冲突' }));
    const drawer = await screen.findByRole('heading', { name: '风险与冲突' });
    expect(drawer).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /退款口径冲突/ }));

    expect(await screen.findByText('形成于')).toBeInTheDocument();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getAllByText('需求收敛').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('退款与冲销在财务侧挂接口径不一致。').length).toBeGreaterThan(0);
  });
});
