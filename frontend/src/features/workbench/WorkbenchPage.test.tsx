import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkbenchPage } from './WorkbenchPage';
import type { ArtifactRecord, ProjectState, ProjectSummary, SourceRecord } from '../../lib/types';

const project: ProjectSummary = {
  id: 'seed-reconciliation',
  name: '业财逐笔对账',
  summary: 'seed',
  status: 'seed',
  scenarioType: 'financial-reconciliation',
  updatedAt: '刚刚'
};

const sources: SourceRecord[] = [
  {
    id: 'src-1',
    name: '订单字段说明.md',
    sourceKind: 'markdown',
    parseStatus: 'parsed',
    syncStatus: 'pending',
    parseSummary: '包含订单号、金额和业务类型字段。'
  }
];

const artifacts: ArtifactRecord[] = [
  {
    id: 'artifact-1',
    artifactType: 'document',
    title: '需求分析文档稿',
    summary: '结构化文档',
    status: 'generated',
    contentFormat: 'json'
  }
];

const state: ProjectState = {
  currentUnderstanding: [{ id: 'u1', title: '当前理解', body: '已形成基础认识' }],
  pendingItems: [],
  confirmedItems: [],
  conflictItems: [],
  mvpItems: [],
  versions: [],
  artifacts: []
};

describe('WorkbenchPage', () => {
  it('marks source and chat fields with stable names', () => {
    render(
      <WorkbenchPage
        project={project}
        sources={sources}
        state={state}
        artifacts={artifacts}
        onCreateTextSource={vi.fn().mockResolvedValue(undefined)}
        onCreateUrlSource={vi.fn().mockResolvedValue(undefined)}
        onCreateFileSource={vi.fn().mockResolvedValue(undefined)}
        onSendChat={vi.fn().mockResolvedValue([])}
        onGenerateArtifact={vi.fn().mockResolvedValue(undefined)}
        onOpenArtifact={vi.fn().mockResolvedValue('{"title":"需求分析文档稿"}')}
      />
    );

    expect(screen.getByLabelText('资料名称')).toHaveAttribute('name', 'sourceName');
    expect(screen.getByLabelText('资料正文')).toHaveAttribute('name', 'sourceText');
    expect(screen.getByLabelText('链接名称')).toHaveAttribute('name', 'urlName');
    expect(screen.getByLabelText('资料链接')).toHaveAttribute('name', 'urlValue');
    expect(screen.getByLabelText('聊天输入')).toHaveAttribute('name', 'chatInput');
  });

  it('submits a text source through the callback', async () => {
    const user = userEvent.setup();
    const onCreateTextSource = vi.fn().mockResolvedValue(undefined);

    render(
      <WorkbenchPage
        project={project}
        sources={sources}
        state={state}
        artifacts={artifacts}
        onCreateTextSource={onCreateTextSource}
        onCreateUrlSource={vi.fn().mockResolvedValue(undefined)}
        onCreateFileSource={vi.fn().mockResolvedValue(undefined)}
        onSendChat={vi.fn().mockResolvedValue([])}
        onGenerateArtifact={vi.fn().mockResolvedValue(undefined)}
        onOpenArtifact={vi.fn().mockResolvedValue('{"title":"需求分析文档稿"}')}
      />
    );

    await user.type(screen.getByLabelText('资料名称'), '补充纪要.txt');
    await user.type(screen.getByLabelText('资料正文'), '逐笔差异需要先找出来。');
    await user.click(screen.getByRole('button', { name: '导入文本资料' }));

    expect(onCreateTextSource).toHaveBeenCalledWith('补充纪要.txt', '逐笔差异需要先找出来。');
  });

  it('sends chat and renders returned message chunks', async () => {
    const user = userEvent.setup();
    const onSendChat = vi.fn().mockResolvedValue([
      {
        event: 'message_chunk',
        data: { text: '先做逐笔差异识别。' }
      }
    ]);

    render(
      <WorkbenchPage
        project={project}
        sources={sources}
        state={state}
        artifacts={artifacts}
        onCreateTextSource={vi.fn().mockResolvedValue(undefined)}
        onCreateUrlSource={vi.fn().mockResolvedValue(undefined)}
        onCreateFileSource={vi.fn().mockResolvedValue(undefined)}
        onSendChat={onSendChat}
        onGenerateArtifact={vi.fn().mockResolvedValue(undefined)}
        onOpenArtifact={vi.fn().mockResolvedValue('{"title":"需求分析文档稿"}')}
      />
    );

    await user.type(screen.getByLabelText('聊天输入'), '请帮我总结当前方向');
    await user.click(screen.getByRole('button', { name: '发送分析请求' }));

    expect(onSendChat).toHaveBeenCalledWith('请帮我总结当前方向', expect.any(Function));
    expect(await screen.findByText('先做逐笔差异识别。')).toBeInTheDocument();
  });

  it('shows source summary preview and opens artifact content', async () => {
    const user = userEvent.setup();
    const onOpenArtifact = vi.fn().mockResolvedValue('{"title":"需求分析文档稿","sections":[]}');

    render(
      <WorkbenchPage
        project={project}
        sources={sources}
        state={state}
        artifacts={artifacts}
        onCreateTextSource={vi.fn().mockResolvedValue(undefined)}
        onCreateUrlSource={vi.fn().mockResolvedValue(undefined)}
        onCreateFileSource={vi.fn().mockResolvedValue(undefined)}
        onSendChat={vi.fn().mockResolvedValue([])}
        onGenerateArtifact={vi.fn().mockResolvedValue(undefined)}
        onOpenArtifact={onOpenArtifact}
      />
    );

    await user.click(screen.getByRole('button', { name: '查看订单字段说明.md摘要' }));
    expect((await screen.findAllByText('包含订单号、金额和业务类型字段。')).length).toBeGreaterThan(1);

    await user.click(screen.getByRole('button', { name: '查看需求分析文档稿' }));
    expect(onOpenArtifact).toHaveBeenCalledWith(artifacts[0]);
    expect((await screen.findAllByText('需求分析文档稿')).length).toBeGreaterThan(1);
  });
});
