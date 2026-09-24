import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { Layout } from '@/components/Layout';

const auth = vi.hoisted(() => ({ user: { full_name: 'Test User' }, role: 'admin', logout: vi.fn() }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
afterEach(cleanup);

it.each(['Admin', 'Account menu'])('offers evaluation navigation to admins through %s', async menu => {
  auth.role = 'admin';
  render(<MemoryRouter><Layout>Workspace</Layout></MemoryRouter>);
  fireEvent.keyDown(screen.getByRole('button', { name: menu }), { key: 'ArrowDown' });
  expect(await screen.findByRole('menuitem', { name: 'AI Evaluations' })).toHaveAttribute('href', '/admin/evals');
});

it.each([
  ['Admin', 'viewer'], ['Admin', 'analyst'], ['Admin', 'member'],
  ['Account menu', 'viewer'], ['Account menu', 'analyst'], ['Account menu', 'member'],
])('hides evaluation navigation in %s for %s', async (menu, role) => {
  auth.role = role;
  render(<MemoryRouter><Layout>Workspace</Layout></MemoryRouter>);
  fireEvent.keyDown(screen.getByRole('button', { name: menu }), { key: 'ArrowDown' });
  await screen.findByRole('menu');
  expect(screen.queryByRole('menuitem', { name: 'AI Evaluations' })).not.toBeInTheDocument();
});
