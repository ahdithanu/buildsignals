import { apiClient } from './client';
import type { CreateTemplate, PreviewRequest, PreviewResponse, PromptContent, TemplateDetail, TemplateSummary } from '@/types/prompts';

const path = (id: string) => `/prompts/${encodeURIComponent(id)}`;

export const promptsApi = {
  list: () => apiClient.get<TemplateSummary[]>('/prompts'),
  create: (data: CreateTemplate) => apiClient.post<TemplateDetail>('/prompts', data),
  detail: (id: string) => apiClient.get<TemplateDetail>(path(id)),
  createVersion: (id: string, data: PromptContent) => apiClient.post<TemplateDetail>(`${path(id)}/versions`, data),
  activate: (id: string, version: number) => apiClient.post<TemplateDetail>(`${path(id)}/versions/${version}/activate`),
  preview: (id: string, data: PreviewRequest) => apiClient.post<PreviewResponse>(`${path(id)}/preview`, data),
};
