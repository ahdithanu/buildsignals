import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render as renderUI, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { parcelsApi } from "@/api/parcels";
import * as parcelMap from "@/components/ParcelMap";

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
const authState = vi.hoisted(() => ({ role: "admin", organizationId: "org-1", userId: "user-1", isDemo: false }));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: authState.userId, full_name: "Test User" },
    organizationId: authState.organizationId,
    role: authState.role,
    isDemo: authState.isDemo,
    isAuthenticated: true,
    logout: vi.fn(),
  }),
}));

import { usePermitBrandMatches } from "@/hooks/usePermitBrandMatches";
import { useNearbyParcels } from "@/hooks/useNearbyParcels";
import { useOrganizationMembers } from "@/hooks/useOrganizationMembers";
import { usePlanningSignals } from "@/hooks/usePlanningSignals";

let queryClient: QueryClient;
function render(ui: ReactNode) {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = queryClient;
  return renderUI(ui, {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
}

// Synthetic contract fixtures, not retained real retail/parcel acceptance evidence.
describe("reviewed nearby parcel anchors (synthetic)", () => {
  const ready = {
    deal_id: "deal-1", anchor_brand_match_id: "match-1", permit_id: "permit-1",
    status: "ready", reason: null, latitude: 37.78, longitude: -122.41,
    method: "reviewed_parcel_centroid", parcel_id: "anchor-parcel-1",
    relationship_id: "relationship-1", permit_raw_record_id: "permit-raw-1",
    parcel_raw_record_id: "parcel-raw-1", permit_normalization_hash: "a".repeat(64),
    parcel_normalization_hash: "b".repeat(64),
  };
  const match = (id = "match-1", permitId = "permit-1") => ({
    id, permit_id: permitId, review_status: "confirmed", brand: { name: "Retailer" },
    permit: { id: permitId, address: "Synthetic retail filing", approval_stage: "pre_approval", latitude: null, longitude: null },
  });
  const panel = () => <MemoryRouter><NearbyParcelsPanel dealId="deal-1" /></MemoryRouter>;
  let create: ReturnType<typeof vi.fn>;
  let get: ReturnType<typeof vi.spyOn>;
  let nearby: ReturnType<typeof useNearbyParcels>;

  beforeEach(() => {
    Object.assign(authState, { role: "admin", organizationId: "org-1", userId: "user-1", isDemo: false });
    vi.mocked(usePlanningSignals).mockReturnValue({ data: [] } as never);
    vi.mocked(useOrganizationMembers).mockReturnValue({ data: [] } as never);
    vi.mocked(usePermitBrandMatches).mockReturnValue({ data: [match(), match("match-2", "permit-2")] } as never);
    create = vi.fn();
    nearby = {
      history: { data: [], isLoading: false }, search: { data: null, isLoading: false },
      create: { mutate: create, isPending: false }, createFromPlanning: { mutate: vi.fn(), isPending: false },
      review: { mutate: vi.fn() }, assign: { mutate: vi.fn() }, promote: { mutate: vi.fn() },
      exportSearch: { mutate: vi.fn() },
    } as unknown as ReturnType<typeof useNearbyParcels>;
    vi.mocked(useNearbyParcels).mockReturnValue(nearby);
    get = vi.spyOn(apiClient, "get").mockResolvedValue(ready);
  });

  afterEach(() => {
    queryClient?.clear();
    vi.restoreAllMocks();
    Object.assign(authState, { role: "admin", organizationId: "org-1", userId: "user-1", isDemo: false });
  });

  it.each([
    ...["parcel_id", "relationship_id", "permit_raw_record_id", "parcel_raw_record_id"].flatMap<[string, Record<string, unknown>]>(field => [
      [`null ${field}`, { [field]: null }],
      [`empty ${field}`, { [field]: "" }],
      [`oversized ${field}`, { [field]: "x".repeat(101) }],
    ]),
    ...["permit_normalization_hash", "parcel_normalization_hash"].flatMap<[string, Record<string, unknown>]>(field => [
      [`null ${field}`, { [field]: null }],
      [`short ${field}`, { [field]: "a".repeat(63) }],
      [`long ${field}`, { [field]: "a".repeat(65) }],
      [`uppercase ${field}`, { [field]: "A".repeat(64) }],
      [`nonhex ${field}`, { [field]: "g".repeat(64) }],
      [`trailing newline ${field}`, { [field]: `${"a".repeat(64)}\n` }],
    ]),
    ["unexpected field", { extra_location: true }],
    ["oversized reason", { reason: "x".repeat(501) }],
    ["empty scope ID", { deal_id: "" }],
    ["oversized scope ID", { permit_id: "x".repeat(101) }],
  ])("rejects malformed reviewed readiness: %s", async (_label, change) => {
    get.mockResolvedValue({ ...ready, ...change });
    await expect(parcelsApi.resolveAnchor("deal-1", "match-1", "permit-1")).rejects.toThrow();
  });

  it.each([
    ["latitude", { latitude: 37.78 }], ["longitude", { longitude: -122.41 }],
    ["method", { method: "source_coordinate" }], ["null reason", { reason: null }],
    ["empty reason", { reason: "" }], ["omitted reason", { reason: undefined }],
    ["unexpected field", { extra_location: true }],
  ])("rejects malformed unavailable readiness: %s", async (_label, change) => {
    get.mockResolvedValue({ ...ready, status: "unavailable", latitude: null, longitude: null,
      method: null, reason: "no_reviewed_parcel", ...change });
    await expect(parcelsApi.resolveAnchor("deal-1", "match-1", "permit-1")).rejects.toThrow();
  });

  it("accepts source-coordinate readiness without reviewed parcel evidence", async () => {
    const source = { ...ready, method: "source_coordinate", parcel_id: null, relationship_id: null,
      permit_raw_record_id: null, parcel_raw_record_id: null,
      permit_normalization_hash: null, parcel_normalization_hash: null };
    get.mockResolvedValue(source);
    await expect(parcelsApi.resolveAnchor("deal-1", "match-1", "permit-1")).resolves.toEqual(source);
  });

  it("resolves only the selected missing-coordinate match and submits full expected_anchor", async () => {
    const map = vi.spyOn(parcelMap, "ParcelMap");
    render(panel());
    expect(screen.getAllByRole("option")).toHaveLength(2);
    await waitFor(() => expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeEnabled());
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/deals/deal-1/nearby-parcel-anchors/match-1");
    expect(queryClient.getQueryCache().getAll().some(query =>
      JSON.stringify(query.queryKey) === JSON.stringify(["nearby-parcel-anchor", "org-1", "user-1", "admin", "deal-1", "match-1"]),
    )).toBe(true);
    expect(screen.getAllByText("Reviewed parcel centroid").length).toBeGreaterThan(0);
    expect(map.mock.lastCall?.[0].center).toMatchObject({ latitude: 37.78, longitude: -122.41, subtitle: "Reviewed parcel centroid" });
    fireEvent.click(screen.getByRole("button", { name: "Search nearby parcels" }));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ anchor_brand_match_id: "match-1", expected_anchor: ready }));
  });

  it("keeps eligible candidate pre-approvals selectable without native coordinates", async () => {
    vi.mocked(usePermitBrandMatches).mockReturnValue({ data: [{ ...match(), review_status: "candidate" }] } as never);
    render(panel());
    expect(screen.getByRole("option", { name: /Pre-approval · Candidate/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeEnabled());
  });

  it("blocks search while loading without fabricating a map and preserves focused drafts", async () => {
    let resolve!: (value: unknown) => void;
    get.mockReturnValue(new Promise(done => { resolve = done; }));
    render(panel());
    expect(screen.getByRole("status")).toHaveTextContent("Resolving parcel search anchor");
    expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeDisabled();
    expect(screen.queryByText("Search Map")).not.toBeInTheDocument();
    const input = screen.getByLabelText("Zoning codes");
    input.focus();
    fireEvent.change(input, { target: { value: "MU, CS" } });
    resolve(ready);
    await waitFor(() => expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeEnabled());
    expect(screen.getByLabelText("Zoning codes")).toBe(input);
    expect(input).toHaveFocus();
    expect(input).toHaveValue("MU, CS");
  });

  it("shows unavailable status and actual permit review link with no fallback pin", async () => {
    get.mockResolvedValue({ ...ready, status: "unavailable", reason: "no_reviewed_parcel", latitude: null, longitude: null, method: null });
    render(panel());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Anchor unavailable"));
    expect(screen.getByRole("status")).toHaveTextContent("no reviewed parcel");
    expect(screen.getByRole("link", { name: "Review permit" })).toHaveAttribute("href", "/permits/permit-1");
    expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeDisabled();
    expect(screen.queryByText("Search Map")).not.toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it.each([
    ["deal", { deal_id: "other-deal" }], ["match", { anchor_brand_match_id: "other-match" }],
    ["permit", { permit_id: "other-permit" }], ["NaN", { latitude: NaN }],
    ["infinite", { longitude: Infinity }], ["out of range", { latitude: 91 }],
    ["missing method", { method: null }],
    ["null reviewed parcel", { parcel_id: null }],
    ["null reviewed relationship", { relationship_id: null }],
    ["null permit raw record", { permit_raw_record_id: null }],
    ["null parcel raw record", { parcel_raw_record_id: null }],
    ["null permit hash", { permit_normalization_hash: null }],
    ["null parcel hash", { parcel_normalization_hash: null }],
    ["malformed hash", { parcel_normalization_hash: "parcel-hash" }],
  ])("rejects a mismatched or invalid %s response", async (_label, change) => {
    get.mockResolvedValue({ ...ready, ...change });
    render(panel());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Anchor unavailable"));
    expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeDisabled();
    expect(screen.queryByText("Search Map")).not.toBeInTheDocument();
    expect(screen.queryByText("Reviewed parcel centroid")).not.toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("does not reuse an anchor across organization, user, role, or selected match", async () => {
    const rendered = render(panel());
    await waitFor(() => expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeEnabled());
    get.mockReturnValue(new Promise(() => {}));
    for (const scope of [{ organizationId: "org-2" }, { userId: "user-2" }, { role: "editor" }]) {
      const before = get.mock.calls.length;
      Object.assign(authState, scope);
      rendered.rerender(panel());
      await waitFor(() => expect(get).toHaveBeenCalledTimes(before + 1));
      expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeDisabled();
      expect(screen.queryByText("Search Map")).not.toBeInTheDocument();
    }
    fireEvent.change(screen.getByLabelText("Signal anchor"), { target: { value: "permit:match-2" } });
    await waitFor(() => expect(get).toHaveBeenLastCalledWith("/deals/deal-1/nearby-parcel-anchors/match-2"));
  });

  it("leaves native coordinates query-free and does not add expected_anchor", () => {
    vi.mocked(usePermitBrandMatches).mockReturnValue({ data: [{ ...match(), permit: { ...match().permit, latitude: 30.26, longitude: -97.74 } }] } as never);
    render(panel());
    fireEvent.click(screen.getByRole("button", { name: "Search nearby parcels" }));
    expect(get).not.toHaveBeenCalled();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0][0]).not.toHaveProperty("expected_anchor");
    expect(screen.queryByText("Reviewed parcel centroid")).not.toBeInTheDocument();
  });

  it.each(["viewer", "demo"])("preserves %s write denial for reviewed anchors", async mode => {
    if (mode === "viewer") authState.role = "viewer";
    else authState.isDemo = true;
    render(panel());
    await screen.findByText("Search Map");
    expect(screen.getByRole("button", { name: "Search nearby parcels" })).toBeDisabled();
    expect(create).not.toHaveBeenCalled();
  });

  it.each(["native selection", "no eligible selection"])("renders persisted reviewed search and candidate provenance with %s", mode => {
    vi.mocked(usePermitBrandMatches).mockReturnValue({ data: mode === "native selection"
      ? [{ ...match("match-2", "permit-2"), permit: { ...match().permit, id: "permit-2", latitude: 30.26, longitude: -97.74 } }] : [] } as never);
    nearby.search.data = {
      id: "saved-1", deal_id: "deal-1", anchor_brand_match_id: "match-1", anchor_permit_id: "permit-1",
      anchor_latitude: ready.latitude, anchor_longitude: ready.longitude, radius_miles: 2, persona: "developer",
      filters: { anchor_resolution: ready }, candidates: [{
        id: "candidate-1", score: 75, score_confidence: 0.8, distance_miles: 0.3,
        review_status: "candidate", explanation: { anchor_resolution: ready }, facts: [],
        parcel: { id: "parcel-1", external_parcel_id: "SYNTHETIC-1", latitude: 37.781, longitude: -122.412, last_verified_at: "2026-11-20" },
      }],
    } as unknown as NonNullable<typeof nearby.search.data>;
    const map = vi.spyOn(parcelMap, "ParcelMap");
    render(panel());
    expect(screen.getAllByText("Reviewed parcel centroid")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Review anchor permit" })).toHaveAttribute("href", "/permits/permit-1");
    expect(screen.getByRole("link", { name: "Open anchor parcel" })).toHaveAttribute("href", "/parcels/anchor-parcel-1");
    expect(map.mock.lastCall?.[0].center).toMatchObject({ latitude: ready.latitude, longitude: ready.longitude, subtitle: "Reviewed parcel centroid" });
    expect(get).not.toHaveBeenCalled();
  });
});

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
