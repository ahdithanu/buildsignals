import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AcquisitionMap from '@/pages/AcquisitionMap';
import Login from '@/pages/Login';
import { signalStageFor } from '@/lib/signalStage';

const login = vi.fn();

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { full_name: 'Alex Rivera', email: 'alex@example.com' },
    role: 'admin',
    organizationId: 'org-1',
    isAuthenticated: false,
    isLoading: false,
    login,
    logout: vi.fn(),
  }),
}));

describe('Build Signals wireframe screens', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps approved parcels available when the acquirable-only map filter is removed', () => {
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: /adjacent parcels/i })).toBeInTheDocument();
    expect(screen.queryByText('Gilbert Land Partners')).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'Acquirable only' })[0]);

    expect(screen.getByText('Gilbert Land Partners')).toBeInTheDocument();
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
  });

  it('submits the redesigned enterprise login form', async () => {
    login.mockResolvedValueOnce(undefined);
    render(<MemoryRouter initialEntries={['/login']}><Login /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText(/work email/i), {
      target: { value: 'alex@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: 'secret-password' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: /keep me signed in/i }));
    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith({
        email: 'alex@example.com',
        password: 'secret-password',
      });
    });
    expect(screen.getByRole('checkbox', { name: /keep me signed in/i })).toHaveAttribute('aria-checked', 'true');
  });

  it('normalizes filing stages from nationwide source labels', () => {
    expect(signalStageFor('pre_approval')).toBe('PRE-APPROVAL');
    expect(signalStageFor('permit-review')).toBe('PRE-APPROVAL');
    expect(signalStageFor('zoning')).toBe('PRE-APPROVAL');
    expect(signalStageFor('approved')).toBe('APPROVED');
    expect(signalStageFor('permit_issued')).toBe('APPROVED');
  });
});
