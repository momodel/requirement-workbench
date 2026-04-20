import userEvent from '@testing-library/user-event';
import { render, screen, waitFor, within } from '@testing-library/react';
import App from './App';

function renderAt(pathname: string) {
  window.history.pushState({}, '', pathname);
  return render(<App />);
}

describe('requirement workbench single-page demo', () => {
  test('home route links into the workbench route', () => {
    renderAt('/');

    expect(
      screen.getByRole('heading', { name: '客户需求转译台' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '进入案例工作台' })).toHaveAttribute(
      'href',
      '/project/reconciliation/workbench'
    );
  });

  test('workbench route renders notebook-style knowledge, chat, and insight areas', () => {
    renderAt('/project/reconciliation/workbench');

    expect(
      screen.getByRole('heading', { name: '项目知识库' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '需求分析对话' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '沉淀总集' })
    ).toBeInTheDocument();
    expect(screen.getByText('订单字段说明.xlsx')).toBeInTheDocument();
    expect(
      screen.getByText(/我们现在对账还是靠人工/)
    ).toBeInTheDocument();
    expect(screen.getByTestId('stage-strip')).toHaveClass('stage-strip-sticky');
    expect(screen.getByTestId('workbench-shell')).toHaveClass('workbench-shell-fixed');
    expect(screen.getByTestId('chat-stream')).toHaveClass('chat-stream-scrollable');
    expect(screen.getByTestId('knowledge-scroll')).toHaveClass('panel-scrollable');
    expect(screen.getByTestId('insight-scroll')).toHaveClass('panel-scrollable');
    expect(screen.getByRole('button', { name: '展开已确认事实' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '展开页面方案 / 交付物' })).toBeInTheDocument();
  });

  test('progress action reveals more turns and advances the stage indicator', async () => {
    const user = userEvent.setup();
    renderAt('/project/reconciliation/workbench');
    const chatStream = screen.getByTestId('chat-stream');

    Object.defineProperty(chatStream, 'scrollHeight', {
      configurable: true,
      value: 1200
    });
    Object.defineProperty(chatStream, 'clientHeight', {
      configurable: true,
      value: 400
    });

    expect(screen.getByText('当前阶段：需求接入')).toBeInTheDocument();
    expect(
      screen.queryByText(/先把对账对象、粒度和科目映射摸清/)
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '继续分析' }));

    expect(
      screen.getByText(/先把对账对象、粒度和科目映射摸清/)
    ).toBeInTheDocument();
    expect(screen.getByText('当前阶段：业务理解')).toBeInTheDocument();
    await waitFor(() => {
      expect(chatStream.scrollTop).toBe(1200);
    });
  });

  test('clicking a knowledge file opens a floating preview', async () => {
    const user = userEvent.setup();
    renderAt('/project/reconciliation/workbench');

    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 1440
    });
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      value: 900
    });

    const fileButton = screen.getByRole('button', { name: /财务科目口径说明\.docx/ });
    Object.defineProperty(fileButton, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        x: 36,
        y: 180,
        top: 180,
        right: 318,
        bottom: 272,
        left: 36,
        width: 282,
        height: 92,
        toJSON: () => ({})
      })
    });

    await user.click(fileButton);

    const preview = screen.getByRole('dialog', {
      name: '文件摘要：财务科目口径说明.docx'
    });
    expect(preview).toHaveClass('knowledge-preview-float', 'knowledge-preview-float-right');
    expect(preview).toHaveStyle({
      position: 'fixed',
      top: '180px',
      left: '330px'
    });
    expect(preview.parentElement).toBe(document.body);
    const previewCard = within(preview).getByText('文件摘要').closest('.preview-card');
    expect(previewCard).toHaveClass('preview-card-solid', 'preview-card-framed');
    expect(preview.querySelector('.preview-card-body')).not.toBeNull();
    expect(getComputedStyle(previewCard as HTMLElement).overflowY).toBe('auto');
    expect(within(preview).getByText('文件摘要')).toBeInTheDocument();
    expect(
      within(preview).getByText(/列出了收入、税额、优惠、退款等对应科目/)
    ).toBeInTheDocument();
  });

  test('switching knowledge files resets preview scroll to the top', async () => {
    const user = userEvent.setup();
    renderAt('/project/reconciliation/workbench');

    await user.click(screen.getByRole('button', { name: /结算单样例-0325\.csv/ }));

    const preview = screen.getByRole('dialog', {
      name: '文件摘要：结算单样例-0325.csv'
    });
    const scrollContainer = preview.querySelector('.preview-card-floating') as HTMLDivElement;

    expect(scrollContainer).not.toBeNull();
    scrollContainer.scrollTop = 168;
    expect(scrollContainer.scrollTop).toBe(168);

    await user.click(screen.getByRole('button', { name: /历史差异清单\.xlsx/ }));

    expect(
      screen.getByRole('dialog', { name: '文件摘要：历史差异清单.xlsx' })
    ).toBeInTheDocument();
    expect(scrollContainer.scrollTop).toBe(0);
  });

  test('delivery artifacts stay empty before final stage and appear after design delivery', async () => {
    const user = userEvent.setup();
    renderAt('/project/reconciliation/workbench');

    await user.click(screen.getByRole('button', { name: '展开页面方案 / 交付物' }));

    const categoryDrawer = screen.getByTestId('insight-drawer-页面方案-交付物');
    expect(within(categoryDrawer).getByText('等待生成')).toBeInTheDocument();
    expect(
      within(categoryDrawer).queryByText('业财对账系统页面方案')
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '继续分析' }));
    await user.click(screen.getByRole('button', { name: '基于当前资料生成理解' }));
    await user.click(screen.getByRole('button', { name: '把本轮结论写入沉淀' }));
    await user.click(screen.getByRole('button', { name: '查看交付建议' }));

    expect(within(categoryDrawer).getByText('业财对账系统页面方案')).toBeInTheDocument();
    expect(within(categoryDrawer).getByText('需求摘要 / MVP / 风险边界')).toBeInTheDocument();
    expect(within(categoryDrawer).getByText('关键交互流')).toBeInTheDocument();
  });

  test('artifact details render document preview and large html prototype overlays', async () => {
    const user = userEvent.setup();
    renderAt('/project/reconciliation/workbench');

    await user.click(screen.getByRole('button', { name: '展开页面方案 / 交付物' }));
    await user.click(screen.getByRole('button', { name: '继续分析' }));
    await user.click(screen.getByRole('button', { name: '基于当前资料生成理解' }));
    await user.click(screen.getByRole('button', { name: '把本轮结论写入沉淀' }));
    await user.click(screen.getByRole('button', { name: '查看交付建议' }));

    await user.click(screen.getByRole('button', { name: '查看需求摘要 / MVP / 风险边界详情' }));

    const detailDrawer = screen.getByRole('complementary', {
      name: '需求摘要 / MVP / 风险边界详情'
    });
    expect(within(detailDrawer).getByText('文档摘要')).toBeInTheDocument();
    expect(within(detailDrawer).getByText('项目背景')).toBeInTheDocument();
    expect(within(detailDrawer).queryByTitle('需求摘要 / MVP / 风险边界原型')).not.toBeInTheDocument();

    await user.click(within(detailDrawer).getByRole('button', { name: '关闭' }));
    await user.click(screen.getByRole('button', { name: '查看业财对账系统页面方案详情' }));

    const pageOverlay = screen.getByRole('dialog', {
      name: '业财对账系统页面方案预览'
    });
    expect(within(pageOverlay).getByText('大图预览')).toBeInTheDocument();
    expect(within(pageOverlay).getByTitle('业财对账系统页面方案原型')).toHaveAttribute(
      'src',
      '/prototypes/reconciliation-pages.html'
    );
    expect(screen.queryByRole('complementary', { name: '业财对账系统页面方案详情' })).not.toBeInTheDocument();

    await user.click(within(pageOverlay).getByRole('button', { name: '关闭' }));
    await user.click(screen.getByRole('button', { name: '查看关键交互流详情' }));

    const flowOverlay = screen.getByRole('dialog', {
      name: '关键交互流预览'
    });
    expect(within(flowOverlay).getByText('大图预览')).toBeInTheDocument();
    expect(within(flowOverlay).getByTitle('关键交互流原型')).toHaveAttribute(
      'src',
      '/prototypes/reconciliation-flow.html'
    );
    expect(screen.queryByRole('complementary', { name: '关键交互流详情' })).not.toBeInTheDocument();
  });
});
