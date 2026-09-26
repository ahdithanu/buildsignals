import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PromptRegistry from '@/pages/PromptRegistry';
import { promptsApi } from '@/api/prompts';
import type { TemplateDetail } from '@/types/prompts';

const auth = vi.hoisted(() => ({ user: { id: 'admin-a' }, organizationId: 'org-a', role: 'admin', isLoading: false, isAuthenticated: true }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <main>{children}</main> }));

const detail: TemplateDetail = {
  id: 'template-1', key: 'permit-check', name: 'Permit check', workflow: 'copilot_answer', description: 'Check evidence', active_version: 1, created_at: '2026-09-23T00:00:00Z',
  versions: [{ id: 'version-1', version: 1, body: 'Status: {{status}}', variables: ['status'], checksum: 'abc123', created_at: '2026-09-23T00:00:00Z', created_by: 'admin-a', activated_at: '2026-09-23T00:00:00Z' }],
  history: [{ id: 'event-1', action: 'activate', version: 1, actor_id: 'admin-a', created_at: '2026-09-23T00:00:00Z' }],
};
const secondVersion: TemplateDetail = { ...detail, versions: [{ ...detail.versions[0], id: 'version-2', version: 2, body: 'New: {{status}}', activated_at: null }, ...detail.versions] };
let client: QueryClient;
function mount() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><PromptRegistry /></QueryClientProvider>);
  return { ...view, rerenderPage: () => view.rerender(<QueryClientProvider client={client}><PromptRegistry /></QueryClientProvider>) };
}
beforeEach(() => {
  Object.assign(auth, { user: { id: 'admin-a' }, organizationId: 'org-a', role: 'admin', isLoading: false, isAuthenticated: true });
  vi.spyOn(promptsApi, 'list').mockResolvedValue([detail]);
  vi.spyOn(promptsApi, 'detail').mockResolvedValue(detail);
  vi.spyOn(promptsApi, 'create').mockResolvedValue(detail);
  vi.spyOn(promptsApi, 'createVersion').mockResolvedValue(secondVersion);
  vi.spyOn(promptsApi, 'activate').mockResolvedValue({ ...secondVersion, active_version: 2 });
  vi.spyOn(promptsApi, 'preview').mockResolvedValue({ rendered: 'Status: pending', version: 1 });
});
afterEach(() => { cleanup(); client?.clear(); vi.restoreAllMocks(); });

describe('Prompt registry', () => {
  it('guards private calls for non-admin and loading sessions', () => {
    auth.role = 'member'; const view = mount();
    expect(screen.getByText('Administrator access is required to view prompts.')).toBeInTheDocument();
    expect(promptsApi.list).not.toHaveBeenCalled();
    auth.role = 'admin'; auth.isLoading = true; view.rerenderPage();
    expect(screen.getByText('Checking access...')).toBeInTheDocument();
    expect(promptsApi.list).not.toHaveBeenCalled();
  });
  it('loads details and displays immutable version history and scope caveat', async () => {
    mount();
    expect(screen.getByText('Loading templates...')).toBeInTheDocument();
    expect(await screen.findByText('Checksum abc123', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/does not alter the deterministic memo\/scoring workflow or invoke an LLM/)).toBeInTheDocument();
    expect(screen.getByText('activate')).toBeInTheDocument();
  });
  it('handles empty list and retryable errors', async () => {
    vi.mocked(promptsApi.list).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce([]);
    mount();
    expect(await screen.findByText('Could not load templates: Offline')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('No prompt templates yet')).toBeInTheDocument();
  });
  it('creates a template with parsed variables', async () => {
    vi.mocked(promptsApi.list).mockResolvedValue([]);
    mount(); await screen.findByText('No prompt templates yet');
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: 'permit-check' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Permit check' } });
    fireEvent.change(screen.getByLabelText('Workflow'), { target: { value: 'copilot_answer' } });
    fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'Status: {{status}}' } });
    fireEvent.change(screen.getByLabelText('Variables (comma separated)'), { target: { value: 'status' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));
    await waitFor(() => expect(promptsApi.create).toHaveBeenCalledWith({ key: 'permit-check', name: 'Permit check', workflow: 'copilot_answer', description: '', body: 'Status: {{status}}', variables: ['status'] }, expect.anything()));
  });
  it('creates a version, previews values, and activates explicitly', async () => {
    mount(); await screen.findByText('Checksum abc123', { exact: false });
    fireEvent.change(screen.getByLabelText('Body', { selector: '#version-body' }), { target: { value: 'New: {{status}}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create version' }));
    await waitFor(() => expect(promptsApi.createVersion).toHaveBeenCalledWith('template-1', { body: 'New: {{status}}', variables: ['status'] }));
    expect(await screen.findByRole('button', { name: 'Activate version' })).toBeInTheDocument();
    expect(screen.getByText(/Active: v1/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Values (JSON object of strings)'), { target: { value: '{"status":"pending"}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await waitFor(() => expect(promptsApi.preview).toHaveBeenCalledWith('template-1', { version: 1, values: { status: 'pending' } }));
    expect(await screen.findByText('Status: pending')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Activate version' }));
    await waitFor(() => expect(promptsApi.activate).toHaveBeenCalledWith('template-1', 2));
    expect(await screen.findByRole('button', { name: 'Rollback to this version' })).toBeInTheDocument();
  });
  it('separates cache by organization', async () => {
    const view = mount(); await screen.findByText('Checksum abc123', { exact: false });
    auth.organizationId = 'org-b'; view.rerenderPage();
    await waitFor(() => expect(promptsApi.list).toHaveBeenCalledTimes(2));
  });
});
