export interface TemplateSummary {
  id: string;
  key: string;
  name: string;
  workflow: string;
  description: string;
  active_version: number | null;
  created_at: string;
}

export interface PromptVersion {
  id: string;
  version: number;
  body: string;
  variables: string[];
  checksum: string;
  created_at: string;
  created_by: string;
  activated_at: string | null;
}

export interface PromptHistoryEvent {
  id: string;
  action: string;
  version: number;
  actor_id: string;
  created_at: string;
}

export interface TemplateDetail extends TemplateSummary {
  versions: PromptVersion[];
  history: PromptHistoryEvent[];
}

export interface PromptContent {
  body: string;
  variables: string[];
}

export interface CreateTemplate extends PromptContent {
  key: string;
  name: string;
  workflow: string;
  description: string;
}

export interface PreviewRequest {
  version: number;
  values: Record<string, string>;
}

export interface PreviewResponse {
  rendered: string;
  version: number;
}
