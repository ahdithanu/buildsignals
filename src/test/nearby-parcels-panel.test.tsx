import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { NearbyParcelsPanel } from "@/components/NearbyParcelsPanel";

vi.mock("@/hooks/usePermitBrandMatches", () => ({
  usePermitBrandMatches: vi.fn(),
}));
vi.mock("@/hooks/useNearbyParcels", () => ({
  useNearbyParcels: vi.fn(),
}));
vi.mock("@/hooks/useOrganizationMembers", () => ({
  useOrganizationMembers: vi.fn(),
}));
vi.mock("@/hooks/usePlanningSignals", () => ({
  usePlanningSignals: vi.fn(),
}));
const authState = vi.hoisted(() => ({ role: "admin" }));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "user-1", full_name: "Test User" },
    organizationId: "org-1",
    role: authState.role,
    isAuthenticated: true,
    logout: vi.fn(),
  }),
}));

import { usePermitBrandMatches } from "@/hooks/usePermitBrandMatches";
import { useNearbyParcels } from "@/hooks/useNearbyParcels";
import { useOrganizationMembers } from "@/hooks/useOrganizationMembers";
import { usePlanningSignals } from "@/hooks/usePlanningSignals";

describe("<NearbyParcelsPanel>", () => {
  beforeEach(() => {
    authState.role = "admin";
    (usePlanningSignals as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
  });

  it("shows the buyer-lens parcel workflow for a geocoded pre-approval signal", () => {
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "match-1",
          review_status: "confirmed",
          confidence: 0.98,
          brand: { name: "Starbucks" },
          permit: {
            address: "100 Main St",
            application_number: "APP-100",
            approval_stage: "pre_approval",
            latitude: 30.2672,
            longitude: -97.7431,
          },
        },
      ],
    });
    (useNearbyParcels as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      history: { data: [] },
      search: {
        data: {
          id: "search-1",
          candidates: [
            {
              id: "candidate-1",
              rank: 1,
              distance_miles: 0.42,
              score: 92.4,
              score_confidence: 0.87,
              explanation: {
                reasons: ["Retail zoning matches buyer lens"],
                cautions: ["Verify frontage access"],
              },
              review_status: "candidate",
              ranker_version: "v1",
              parcel: {
                id: "parcel-1",
                external_parcel_id: "PARCEL-001",
                address: "125 Main St",
                city: "Austin",
                state: "TX",
                latitude: 30.2672,
                longitude: -97.7431,
                land_area_sq_ft: 52000,
                land_use: "Retail",
                zoning_code: "CS",
                last_verified_at: "2026-07-23T00:00:00Z",
              },
              facts: [
                {
                  id: "fact-1",
                  fact_type: "ownership",
                  value: { owner_name: "Main Street Holdings" },
                  source_url: "https://example.gov/parcels/1",
                  excerpt: "Ownership record",
                  confidence: 1,
                  observed_at: "2026-07-23T00:00:00Z",
                  last_verified_at: "2026-07-23T00:00:00Z",
                },
              ],
            },
          ],
          radius_miles: 2,
          persona: "developer",
        },
        isLoading: false,
        error: null,
      },
      create: { isPending: false, mutate: vi.fn(), error: null },
      createFromPlanning: { isPending: false, mutate: vi.fn(), error: null },
      review: { isPending: false, mutate: vi.fn() },
      assign: { isPending: false, mutate: vi.fn(), error: null },
      promote: { isPending: false, mutate: vi.fn(), error: null },
    });
    (useOrganizationMembers as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        { user_id: "user-1", full_name: "Test User", is_default: true },
        { user_id: "user-2", full_name: "Teammate", is_default: false },
      ],
    });

    const rendered = render(
      <MemoryRouter>
        <NearbyParcelsPanel dealId="deal-1" />
      </MemoryRouter>,
    );

    expect(screen.getByText("Nearby Parcels")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /buyer lens selector/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Developer" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Investor" })).toBeInTheDocument();
    expect(screen.getByText("Search Map")).toBeInTheDocument();
    expect(screen.getByText("Best developer fit")).toBeInTheDocument();
    expect(screen.getAllByText("0.42 mi")).toHaveLength(2);
    expect(screen.getAllByText("Retail zoning matches buyer lens")).toHaveLength(2);
    expect(screen.getAllByText("Verify frontage access")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /open source evidence/i })).toHaveAttribute(
      "href",
      "https://example.gov/parcels/1",
    );
    expect(screen.getByRole("button", { name: /shortlist parcel/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /dismiss parcel/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /assign parcel/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /promote opportunity/i })).toBeDisabled();

    expect(screen.getByText(/Owner record:/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /open parcel/i })).toHaveLength(2);
    expect(screen.getByRole("button", { name: /export nearby parcels/i })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Broker" }));
    fireEvent.change(screen.getByRole("slider"), { target: { value: '4' } });
    expect(screen.getByText("Saved search · Radius 2.00 mi · developer lens")).toBeInTheDocument();
    expect(screen.getByText("Best developer fit")).toBeInTheDocument();
    expect(screen.queryByText("Best broker fit")).not.toBeInTheDocument();

    authState.role = "viewer";
    rendered.rerender(
      <MemoryRouter>
        <NearbyParcelsPanel dealId="deal-1" />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: /export nearby parcels/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /search nearby parcels/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /shortlist parcel/i })).toBeDisabled();
  });

  it("exports the current nearby parcel results", () => {
    const createObjectURL = vi.fn(() => "blob:nearby-parcels");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      configurable: true,
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const exportMutate = vi.fn((_searchId, options) => options.onSuccess({
      blob: new Blob(["server-authorized-export"]),
      filename: "reviewed-parcels.csv",
      exportedCount: 1,
      omittedCount: 0,
    }));

    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "match-1",
          review_status: "confirmed",
          confidence: 0.98,
          brand: { name: "Starbucks" },
          permit: {
            address: "100 Main St",
            application_number: "APP-100",
            approval_stage: "pre_approval",
            latitude: 30.2672,
            longitude: -97.7431,
          },
        },
      ],
    });
    (useNearbyParcels as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      history: { data: [] },
      search: {
        data: {
          id: "search-1",
          candidates: [
            {
              id: "candidate-1",
              rank: 1,
              distance_miles: 0.42,
              score: 92.4,
              score_confidence: 0.87,
              explanation: {
                reasons: ["Retail zoning matches buyer lens"],
                cautions: ["Verify frontage access"],
              },
              review_status: "candidate",
              ranker_version: "v1",
              parcel: {
                id: "parcel-1",
                external_parcel_id: "PARCEL-001",
                address: "125 Main St",
                city: "Austin",
                state: "TX",
                latitude: 30.2672,
                longitude: -97.7431,
                land_area_sq_ft: 52000,
                land_use: "Retail",
                zoning_code: "CS",
                last_verified_at: "2026-07-23T00:00:00Z",
              },
              facts: [],
            },
          ],
          radius_miles: 2,
          persona: "developer",
        },
        isLoading: false,
        error: null,
      },
      create: { isPending: false, mutate: vi.fn(), error: null },
      createFromPlanning: { isPending: false, mutate: vi.fn(), error: null },
      review: { isPending: false, mutate: vi.fn() },
      assign: { isPending: false, mutate: vi.fn(), error: null },
      promote: { isPending: false, mutate: vi.fn(), error: null },
      exportSearch: { isPending: false, mutate: exportMutate, error: null },
    });
    (useOrganizationMembers as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        { user_id: "user-1", full_name: "Test User", is_default: true },
        { user_id: "user-2", full_name: "Teammate", is_default: false },
      ],
    });

    render(
      <MemoryRouter>
        <NearbyParcelsPanel dealId="deal-1" />
      </MemoryRouter>,
    );

    screen.getByRole("button", { name: /export nearby parcels/i }).click();

    expect(exportMutate).toHaveBeenCalledWith("search-1", expect.any(Object));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:nearby-parcels");
  });

  it("submits buyer-lens filters with the nearby parcel search", () => {
    const createMutate = vi.fn();
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "match-1",
          review_status: "confirmed",
          confidence: 0.98,
          brand: { name: "Starbucks" },
          permit: {
            address: "100 Main St",
            application_number: "APP-100",
            approval_stage: "pre_approval",
            latitude: 30.2672,
            longitude: -97.7431,
          },
        },
      ],
    });
    (useNearbyParcels as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      history: { data: [] },
      search: {
        data: null,
        isLoading: false,
        error: null,
      },
      create: { isPending: false, mutate: createMutate, error: null },
      createFromPlanning: { isPending: false, mutate: vi.fn(), error: null },
      review: { isPending: false, mutate: vi.fn() },
      assign: { isPending: false, mutate: vi.fn(), error: null },
      promote: { isPending: false, mutate: vi.fn(), error: null },
    });
    (useOrganizationMembers as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
    });

    render(
      <MemoryRouter>
        <NearbyParcelsPanel dealId="deal-1" />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/min land area/i), { target: { value: "50000" } });
    fireEvent.change(screen.getByLabelText(/zoning codes/i), { target: { value: "CS, MU" } });
    fireEvent.change(screen.getByLabelText(/land uses/i), { target: { value: "Retail, Office" } });
    fireEvent.change(screen.getByLabelText(/result cap/i), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: /search nearby parcels/i }));

    expect(createMutate).toHaveBeenCalledWith({
      anchor_brand_match_id: "match-1",
      radius_miles: 2,
      persona: "developer",
      limit: 12,
      minimum_land_area_sq_ft: 50000,
      zoning_codes: ["CS", "MU"],
      land_uses: ["Retail", "Office"],
    });
  });

  it("runs a planning-anchored nearby parcel search from a geocoded planning signal", () => {
    const createFromPlanning = vi.fn();
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    (usePlanningSignals as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "planning-1",
          source_id: "source-1",
          external_record_id: "PLAN-1",
          event_type: "planning_hearing_agenda_item",
          stage: "pre_approval",
          title: "Rezoning for neighborhood retail",
          address: "200 Main St",
          city: "Austin",
          state: "TX",
          latitude: 30.27,
          longitude: -97.74,
          signal_categories: ["retail"],
          priority_reasons: [],
          priority_score: 82,
          confidence: 0.9,
          first_seen_at: "2026-09-01T00:00:00Z",
          last_seen_at: "2026-09-01T00:00:00Z",
          latest_raw_record: {
            id: "raw-1",
            external_record_id: "PLAN-1",
            content_hash: "hash",
            received_at: "2026-09-01T00:00:00Z",
          },
          company_matches: [],
        },
      ],
    });
    (useNearbyParcels as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      history: { data: [] },
      search: {
        data: null,
        isLoading: false,
        error: null,
      },
      create: { isPending: false, mutate: vi.fn(), error: null },
      createFromPlanning: { isPending: false, mutate: createFromPlanning, error: null },
      review: { isPending: false, mutate: vi.fn() },
      assign: { isPending: false, mutate: vi.fn(), error: null },
      promote: { isPending: false, mutate: vi.fn(), error: null },
      exportSearch: { isPending: false, mutate: vi.fn(), error: null },
    });
    (useOrganizationMembers as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });

    render(
      <MemoryRouter>
        <NearbyParcelsPanel
          dealId="deal-1"
          deal={{
            id: "deal-1",
            name: "Austin retail pursuit",
            address: "200 Main St",
            market: "Austin, TX",
            assetClass: "retail",
            askingPrice: 0,
            noi: null,
            dealScore: 0,
            projectedIrr: null,
            equityMultiple: null,
            riskLevel: "medium",
            status: "new",
            source: "",
            broker: "",
            yearBuilt: 0,
            units: 0,
            squareFeet: 0,
            summary: "",
            thesis: "",
            risks: [],
            riskFlags: [],
            nextSteps: [],
            signals: [],
            documents: [],
            assumptions: {
              purchasePrice: 0,
              closingCosts: 0,
              renovationCost: 0,
              exitCapRate: 0,
              holdPeriod: 0,
              rentGrowth: 0,
              vacancy: 0,
              opexRatio: 0,
              ltv: 0,
              interestRate: 0,
              stabilizationMonths: 0,
            },
            memo: {
              executiveSummary: "",
              whyThisDeal: "",
              propertyOverview: "",
              marketOverview: "",
              financialSummary: "",
              risksAndMitigants: "",
              valueCreationPlan: "",
              recommendedAction: "",
            },
            activity: [],
            lastUpdated: "",
            dueDate: "",
            owner: "",
            cashOnCash: null,
            subscores: null,
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("option", { name: /Planning · Rezoning for neighborhood retail/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/signal anchor/i), { target: { value: "planning:planning-1" } });
    fireEvent.click(screen.getByRole("button", { name: /search nearby parcels/i }));

    expect(createFromPlanning).toHaveBeenCalledWith({
      planningRecordId: "planning-1",
      payload: {
        radius_miles: 2,
        persona: "developer",
        limit: 50,
        minimum_land_area_sq_ft: undefined,
        zoning_codes: [],
        land_uses: [],
      },
    });
  });

  it("assigns a shortlisted parcel to a teammate", () => {
    const assign = vi.fn();
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "match-1",
          review_status: "confirmed",
          confidence: 0.98,
          brand: { name: "Starbucks" },
          permit: {
            address: "100 Main St",
            application_number: "APP-100",
            approval_stage: "pre_approval",
            latitude: 30.2672,
            longitude: -97.7431,
          },
        },
      ],
    });
    (useNearbyParcels as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      history: { data: [] },
      search: {
        data: {
          id: "search-1",
          candidates: [
            {
              id: "candidate-1",
              rank: 1,
              distance_miles: 0.42,
              score: 92.4,
              score_confidence: 0.87,
              explanation: {
                reasons: ["Retail zoning matches buyer lens"],
                cautions: ["Verify frontage access"],
              },
              review_status: "shortlisted",
              ranker_version: "v1",
              parcel: {
                id: "parcel-1",
                external_parcel_id: "PARCEL-001",
                address: "125 Main St",
                city: "Austin",
                state: "TX",
                latitude: 30.2672,
                longitude: -97.7431,
                land_area_sq_ft: 52000,
                land_use: "Retail",
                zoning_code: "CS",
                last_verified_at: "2026-07-23T00:00:00Z",
              },
              facts: [],
            },
          ],
          radius_miles: 2,
          persona: "developer",
        },
        isLoading: false,
        error: null,
      },
      create: { isPending: false, mutate: vi.fn(), error: null },
      createFromPlanning: { isPending: false, mutate: vi.fn(), error: null },
      review: { isPending: false, mutate: vi.fn() },
      assign: { isPending: false, mutate: assign, error: null },
      promote: { isPending: false, mutate: vi.fn(), error: null },
    });
    (useOrganizationMembers as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        { user_id: "user-1", full_name: "Test User", is_default: true },
        { user_id: "user-2", full_name: "Teammate", is_default: false },
      ],
    });

    render(
      <MemoryRouter>
        <NearbyParcelsPanel dealId="deal-1" />
      </MemoryRouter>,
    );

    screen.getByRole("button", { name: /assign parcel/i }).click();

    expect(assign).toHaveBeenCalledWith({
      candidateId: "candidate-1",
      payload: { assigned_to_user_id: "user-1" },
    });
  });

  it("promotes a shortlisted parcel into a live opportunity", () => {
    const promote = vi.fn();
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "match-1",
          review_status: "confirmed",
          confidence: 0.98,
          brand: { name: "Starbucks" },
          permit: {
            address: "100 Main St",
            application_number: "APP-100",
            approval_stage: "pre_approval",
            latitude: 30.2672,
            longitude: -97.7431,
          },
        },
      ],
    });
    (useNearbyParcels as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      history: { data: [] },
      search: {
        data: {
          id: "search-1",
          candidates: [
            {
              id: "candidate-1",
              rank: 1,
              distance_miles: 0.42,
              score: 92.4,
              score_confidence: 0.87,
              explanation: {
                reasons: ["Retail zoning matches buyer lens"],
                cautions: ["Verify frontage access"],
              },
              review_status: "shortlisted",
              ranker_version: "v1",
              parcel: {
                id: "parcel-1",
                external_parcel_id: "PARCEL-001",
                address: "125 Main St",
                city: "Austin",
                state: "TX",
                latitude: 30.2672,
                longitude: -97.7431,
                land_area_sq_ft: 52000,
                land_use: "Retail",
                zoning_code: "CS",
                last_verified_at: "2026-07-23T00:00:00Z",
              },
              facts: [],
            },
          ],
          radius_miles: 2,
          persona: "developer",
        },
        isLoading: false,
        error: null,
      },
      create: { isPending: false, mutate: vi.fn(), error: null },
      createFromPlanning: { isPending: false, mutate: vi.fn(), error: null },
      review: { isPending: false, mutate: vi.fn() },
      assign: { isPending: false, mutate: vi.fn(), error: null },
      promote: { isPending: false, mutate: promote, error: null },
    });
    (useOrganizationMembers as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        { user_id: "user-1", full_name: "Test User", is_default: true },
        { user_id: "user-2", full_name: "Teammate", is_default: false },
      ],
    });

    render(
      <MemoryRouter>
        <NearbyParcelsPanel dealId="deal-1" />
      </MemoryRouter>,
    );

    screen.getByRole("button", { name: /promote opportunity/i }).click();

    expect(promote.mock.calls[0][0]).toEqual({
      candidateId: "candidate-1",
      payload: { name: "125 Main St" },
    });
  });
});
