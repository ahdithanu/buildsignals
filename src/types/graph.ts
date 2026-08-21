import type { PermitBrandMatch } from './brand';

export type GraphEntityType =
  | 'opportunity'
  | 'permit'
  | 'parcel'
  | 'property'
  | 'developer'
  | 'owner'
  | 'general_contractor'
  | 'architect'
  | 'engineer'
  | 'city'
  | 'lender'
  | 'broker'
  | 'company'
  | 'person'
  | 'source_record';

export type GraphRelationshipType =
  | 'located_on'
  | 'owns'
  | 'owned_by'
  | 'developed_by'
  | 'developer_of'
  | 'contracted_by'
  | 'contractor_for'
  | 'designed_by'
  | 'engineer_for'
  | 'permitted_by'
  | 'permit_for'
  | 'financed_by'
  | 'brokered_by'
  | 'related_to';

export interface GraphEntity {
  id: string;
  entity_type: GraphEntityType;
  display_name: string;
  normalized_name?: string;
  normalized_address?: string | null;
  source_system?: string | null;
  source_id?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  zip_code?: string | null;
  attributes?: Record<string, unknown> | null;
  confidence: number;
  created_at?: string;
  updated_at?: string;
  last_verified_at: string;
}

export interface GraphEvidence {
  id: string;
  source_system: string;
  source_id?: string | null;
  source_url?: string | null;
  evidence_type?: string | null;
  excerpt?: string | null;
  observed_at?: string | null;
  confidence: number;
  payload?: Record<string, unknown> | null;
  created_at: string;
}

export interface GraphRelationship {
  id: string;
  relationship_type: GraphRelationshipType;
  confidence: number;
  source_system?: string | null;
  source_id?: string | null;
  attributes?: Record<string, unknown> | null;
  is_current?: boolean;
  valid_from?: string;
  valid_to?: string | null;
  updated_at?: string;
  created_at: string;
  last_verified_at: string;
  evidence: GraphEvidence[];
}

export interface GraphRelatedEntity {
  entity: GraphEntity;
  relationship: GraphRelationship;
  direction: 'incoming' | 'outgoing';
}

export interface GraphEntityDetail extends GraphEntity {
  aliases: string[];
  source_identities?: {
    source_system: string;
    source_id: string;
    confidence: number;
    last_verified_at: string;
  }[];
  links: {
    record_type: string;
    record_id: string;
  }[];
  related: GraphRelatedEntity[];
}

export interface GraphEntitySearchResult extends GraphEntity {
  aliases: string[];
}

export interface GraphEntityMergeCandidate {
  entity: GraphEntity;
  score: number;
  reasons: string[];
}

export interface GraphEntityMergeResult {
  merge_id: string;
  merged_entity_id: string;
  survivor: GraphEntity;
  aliases_moved: number;
  source_identities_moved: number;
  links_moved: number;
  relationships_rewired: number;
  relationships_collapsed: number;
  evidence_moved: number;
  created_at: string;
}

export interface GraphRelationshipDetail {
  relationship: GraphRelationship;
  source_entity: GraphEntity;
  target_entity: GraphEntity;
}

export interface GraphPath {
  entities: GraphEntity[];
  relationships: GraphRelationship[];
}

export interface OpportunityGraphContext {
  opportunity_id: string;
  root_entities: GraphEntity[];
  nearby_parcel_searches: number;
  buyer_lenses: {
    persona: string;
    search_count: number;
    latest_radius_miles: number;
    latest_created_at: string;
    top_parcels: {
      parcel_id: string;
      external_parcel_id: string;
      address?: string | null;
      city?: string | null;
      state?: string | null;
      distance_miles: number;
      score: number;
      rank: number;
    }[];
  }[];
  shared_parcels: {
    parcel_id: string;
    external_parcel_id: string;
    address?: string | null;
    city?: string | null;
    state?: string | null;
    best_distance_miles: number;
    best_score: number;
    best_persona: string;
    personas: string[];
    lens_count: number;
  }[];
  permit_brand_matches: PermitBrandMatch[];
  companies: GraphRelatedEntity[];
  developers: GraphRelatedEntity[];
  parcels: GraphRelatedEntity[];
  owners: GraphRelatedEntity[];
  contractors: GraphRelatedEntity[];
  architects: GraphRelatedEntity[];
  engineers: GraphRelatedEntity[];
  permits: GraphRelatedEntity[];
  cities: GraphRelatedEntity[];
  lenders: GraphRelatedEntity[];
  brokers: GraphRelatedEntity[];
  other: GraphRelatedEntity[];
}
