import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ProjectsPage } from './ProjectsPage';

describe('ProjectsPage', () => {
  it('marks project form fields with stable names', () => {
    render(
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <ProjectsPage
          projects={[]}
          onCreateProject={vi.fn().mockResolvedValue(undefined)}
        />
      </MemoryRouter>
    );

    expect(screen.getByLabelText('项目名称')).toHaveAttribute('name', 'projectName');
    expect(screen.getByLabelText('项目摘要')).toHaveAttribute('name', 'projectSummary');
  });

  it('submits project creation through callback', async () => {
    const user = userEvent.setup();
    const onCreateProject = vi.fn().mockResolvedValue(undefined);

    render(
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <ProjectsPage
          projects={[
            {
              id: 'seed-reconciliation',
              name: '业财逐笔对账',
              summary: 'seed',
              status: 'seed',
              scenarioType: 'financial-reconciliation',
              updatedAt: '刚刚'
            }
          ]}
          onCreateProject={onCreateProject}
        />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText('项目名称'), '结算对账分析');
    await user.type(screen.getByLabelText('项目摘要'), '新的项目');
    await user.click(screen.getByRole('button', { name: '新建项目' }));

    expect(onCreateProject).toHaveBeenCalledWith(
      '结算对账分析',
      '新的项目',
      'general-requirement'
    );
  });
});
