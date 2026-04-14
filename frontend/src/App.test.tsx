import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders home title', async () => {
    render(<App />);
    expect(await screen.findByText('客户需求转译台')).toBeInTheDocument();
  });
});
