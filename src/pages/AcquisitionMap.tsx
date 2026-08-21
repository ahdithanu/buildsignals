import { useMemo, useState } from "react";
import {
  Check,
  CircleDollarSign,
  Download,
  Layers3,
  MapPin,
  MousePointer2,
  Radius,
  Users,
} from "lucide-react";
import { Layout } from "@/components/Layout";
import { cn } from "@/lib/utils";

const mapSignals = [
  { id: "sprouts", name: "Sprouts — Gilbert Crossing", market: "Gilbert · site plan filed 8/11", score: 92, stage: "pre" },
  { id: "cold", name: "Cold-storage build, 41 ac", market: "Wilmer · in review 3d", score: 86, stage: "pre" },
  { id: "dutch", name: "Dutch Bros — Loop 1604", market: "San Antonio · permit issued", score: 81, stage: "approved" },
  { id: "grocery", name: "Grocery pad split, 6 ac", market: "Mesa · plat filed 5d", score: 61, stage: "pre" },
  { id: "qsr", name: "Unnamed QSR pad", market: "Chandler · pre-application", score: 57, stage: "pre" },
];

const parcels = [
  { id: "304-55-013", owner: "Val Vista Grove LLC", size: 2.1, zoning: "C-2", status: "Listed", reason: "74 days on market · $2.4M", score: 94, evidence: "MLS 6712334 · Cushman", transfer: "$1.05M · Mar 2016" },
  { id: "304-55-014", owner: "Hensley Family Trust", size: 3.4, zoning: "R-4", status: "Off-market", reason: "Held 22 yrs · absentee · trustee on file", score: 88, evidence: "Recorder · trustee verified", transfer: "$620K · Sep 2004" },
  { id: "304-55-021", owner: "Val Vista Grove LLC", size: 1.2, zoning: "C-2", status: "Off-market", reason: "Same owner as 013 · one negotiation", score: 83, evidence: "Assessor + recorder", transfer: "$480K · Mar 2016" },
  { id: "304-56-002", owner: "R. & M. Okafor", size: 0.9, zoning: "C-1", status: "Distressed", reason: "Tax delinquent 2 yrs · lien 6/09", score: 71, evidence: "County tax lien", transfer: "$310K · Jun 2012" },
  { id: "304-55-018", owner: "Gilbert Land Partners", size: 5, zoning: "C-2", status: "Not available", reason: "Under contract 7/30", score: null, evidence: "Recorder notice", transfer: "$2.8M · Jul 2026" },
];

const availabilityFilters = ["Acquirable only", "Listed for sale", "Owner reachable", "Held 10+ yrs", "Absentee owner", "Tax delinquent"];

export default function AcquisitionRadar() {
  const [selectedSignalId, setSelectedSignalId] = useState("sprouts");
  const [selectedParcelId, setSelectedParcelId] = useState("304-55-013");
  const [assemblage, setAssemblage] = useState<Set<string>>(new Set(["304-55-013", "304-55-014", "304-55-021"]));
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set(["Acquirable only"]));
  const [acquirableOnly, setAcquirableOnly] = useState(true);

  const selectedSignal = mapSignals.find((signal) => signal.id === selectedSignalId) || mapSignals[0];
  const selectedParcel = parcels.find((parcel) => parcel.id === selectedParcelId) || parcels[0];
  const visibleParcels = acquirableOnly ? parcels.filter((parcel) => parcel.status !== "Not available") : parcels;
  const selectedAcreage = useMemo(
    () => parcels.filter((parcel) => assemblage.has(parcel.id)).reduce((sum, parcel) => sum + parcel.size, 0),
    [assemblage],
  );

  function toggleFilter(filter: string) {
    setActiveFilters((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  }

  function toggleParcel(id: string) {
    setAssemblage((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Layout>
      <div className="grid min-h-[calc(100vh-48px)] lg:grid-cols-[344px_1fr]">
        <aside className="hidden min-h-0 border-r-2 border-foreground bg-card lg:flex lg:flex-col">
          <div className="border-b-2 border-foreground p-3">
            <div className="flex items-center justify-between"><p className="section-label text-foreground">Signals in view</p><span className="text-[9px] text-muted-foreground">42 total</span></div>
            <div className="mt-2 flex flex-wrap gap-1">
              <button className="bg-foreground px-2 py-1 text-[9px] font-semibold text-background">With acquirable land</button>
              <button className="border border-input bg-background px-2 py-1 text-[9px]">Pre-approval</button>
              <button className="border border-input bg-background px-2 py-1 text-[9px]">Priority 70+</button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {mapSignals.map((signal) => (
              <button
                type="button"
                key={signal.id}
                onClick={() => setSelectedSignalId(signal.id)}
                className={cn(
                  "w-full border-b border-border px-3 py-3 text-left hover:bg-secondary",
                  signal.stage === "pre" && "border-l-2 border-l-destructive",
                  selectedSignal.id === signal.id && "bg-secondary",
                )}
              >
                <span className="flex items-start justify-between gap-3"><span className="text-xs font-semibold">{signal.name}</span><span className="text-xs font-semibold">{signal.score}</span></span>
                <span className="mt-1 block text-[10px] text-muted-foreground">{signal.market}</span>
              </button>
            ))}
          </div>
          <div className="border-t-2 border-foreground p-3">
            <p className="section-label">Layers</p>
            <div className="mt-2 space-y-1.5 text-[10px]">
              <Legend tone="bg-destructive" label="Pre-approval signals" />
              <Legend tone="bg-foreground" label="Approved / issued" />
              <Legend tone="border-2 border-dashed border-foreground" label="Acquirable — listed" />
              <Legend tone="border-2 border-dotted border-muted-foreground" label="Acquirable — off-market" />
              <Legend tone="bg-border" label="Not available" />
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <section className="relative h-[300px] shrink-0 overflow-hidden border-b-2 border-foreground bg-secondary md:h-[390px] lg:min-h-[340px] lg:flex-1">
            <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(hsl(var(--border))_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border))_1px,transparent_1px)] [background-size:46px_46px]" />
            <div className="absolute left-[18%] top-[18%] h-[35%] w-[28%] border-2 border-dashed border-muted-foreground" />
            <ParcelShape className="left-[24%] top-[51%] h-[18%] w-[13%] border-dashed bg-card" label="013 · listed" selected={selectedParcel.id === "304-55-013"} onClick={() => setSelectedParcelId("304-55-013")} />
            <ParcelShape className="left-[38%] top-[53%] h-[16%] w-[12%] border-dotted" label="014 · off-mkt" selected={selectedParcel.id === "304-55-014"} onClick={() => setSelectedParcelId("304-55-014")} />
            <ParcelShape className="left-[25%] top-[71%] h-[11%] w-[9%] border-dotted" label="021" selected={selectedParcel.id === "304-55-021"} onClick={() => setSelectedParcelId("304-55-021")} />
            <div className="absolute left-[36%] top-[72%] h-[10%] w-[10%] bg-border p-1 text-[8px] text-muted-foreground">018 · n/a</div>
            <MapSignal className="left-[32%] top-[36%] bg-destructive" label={selectedSignal.name} />
            <MapSignal className="left-[62%] top-[26%] bg-foreground" />
            <MapSignal className="left-[73%] top-[65%] bg-destructive" />
            <MapSignal className="left-[16%] top-[28%] bg-foreground" />

            <div className="absolute right-3 top-3 flex flex-col gap-1.5">
              <MapTool icon={Radius} label="Draw radius" />
              <MapTool icon={MousePointer2} label="Assemblage mode" />
              <button type="button" onClick={() => setAcquirableOnly((value) => !value)} className={cn("inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-2 text-[9px] font-semibold", acquirableOnly && "bg-foreground text-background")}><Layers3 className="h-3 w-3" /> Acquirable only</button>
            </div>
            <div className="absolute bottom-3 left-3 border border-input bg-card px-2 py-1 text-[9px] text-muted-foreground">Phoenix metro · 42 signals · 11 adjacent parcels · 4 acquirable</div>
          </section>

          <section className="grid min-h-0 bg-background xl:grid-cols-[1fr_296px]">
            <div className="min-w-0 border-foreground p-3 xl:border-r-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h1 className="text-xs font-semibold md:text-sm">Adjacent parcels — acquirable near {selectedSignal.name}</h1>
                <p className="text-[9px] text-muted-foreground">within 0.5 mi · 11 parcels · {visibleParcels.length} shown</p>
              </div>
              <div className="mt-2 flex gap-1 overflow-x-auto pb-1">
                {availabilityFilters.map((filter) => (
                  <button key={filter} type="button" onClick={() => toggleFilter(filter)} className={cn("shrink-0 border border-input bg-card px-2 py-1 text-[9px]", activeFilters.has(filter) && "border-foreground bg-foreground text-background")}>{filter}</button>
                ))}
              </div>

              <div className="mt-2 overflow-x-auto">
                <div className="min-w-[760px]">
                  <div className="grid grid-cols-[90px_1fr_55px_65px_80px_1.3fr_44px_54px] gap-2 border-b-2 border-foreground py-2 text-[8px] font-semibold uppercase text-muted-foreground">
                    <span>APN</span><span>Owner of record</span><span>Size</span><span>Zoning</span><span>Status</span><span>Why gettable</span><span>Fit</span><span />
                  </div>
                  {visibleParcels.map((parcel) => (
                    <button
                      type="button"
                      key={parcel.id}
                      onClick={() => setSelectedParcelId(parcel.id)}
                      className={cn("grid w-full grid-cols-[90px_1fr_55px_65px_80px_1.3fr_44px_54px] items-center gap-2 border-b border-border py-2 text-left text-[10px] hover:bg-secondary", selectedParcel.id === parcel.id && "bg-secondary")}
                    >
                      <span className="font-mono text-[9px]">{parcel.id}</span><span className="font-semibold">{parcel.owner}</span><span>{parcel.size} ac</span><span>{parcel.zoning}</span><span className={parcel.status === "Distressed" ? "font-semibold text-destructive" : "font-semibold"}>{parcel.status}</span><span className="text-muted-foreground">{parcel.reason}</span><span className="font-semibold">{parcel.score ?? "—"}</span>
                      <span
                        role="checkbox"
                        aria-checked={assemblage.has(parcel.id)}
                        onClick={(event) => { event.stopPropagation(); toggleParcel(parcel.id); }}
                        className={cn("inline-flex h-6 items-center justify-center border border-foreground text-[9px] font-semibold", assemblage.has(parcel.id) && "bg-foreground text-background")}
                      >
                        {assemblage.has(parcel.id) ? <Check className="h-3 w-3" /> : "Add"}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2 border-t-2 border-foreground pt-2">
                <button type="button" className="inline-flex h-8 items-center gap-1.5 bg-foreground px-3 text-[10px] font-semibold text-background"><Users className="h-3.5 w-3.5" />Build assemblage ({assemblage.size} selected · {selectedAcreage.toFixed(1)} ac)</button>
                <button type="button" className="inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-3 text-[10px] font-semibold"><Download className="h-3.5 w-3.5" />Export owner contacts</button>
                <p className="text-[9px] text-muted-foreground">Ownership verified 8/12 · assessor + recorder</p>
              </div>
            </div>

            <aside className="border-t-2 border-foreground bg-card p-3 xl:border-t-0">
              <p className="section-label">Selected parcel — {selectedParcel.id}</p>
              <h2 className="mt-2 text-xs font-semibold">{selectedParcel.owner}</h2>
              <p className="mt-1 text-[10px] text-muted-foreground">{selectedParcel.size} ac · {selectedParcel.zoning} · 0.1 mi from signal</p>
              <div className="mt-3 border-t-2 border-foreground">
                <ParcelFact label="Availability" value={`${selectedParcel.status} · ${selectedParcel.reason}`} />
                <ParcelFact label="Evidence" value={selectedParcel.evidence} />
                <ParcelFact label="Last transfer" value={selectedParcel.transfer} />
                <ParcelFact label="Encumbrances" value={selectedParcel.status === "Distressed" ? "Tax lien recorded" : "None of record"} />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <button type="button" className="inline-flex h-8 items-center gap-1.5 bg-foreground px-2.5 text-[9px] font-semibold text-background"><CircleDollarSign className="h-3.5 w-3.5" />Contact owner</button>
                <button type="button" className="h-8 border border-foreground px-2.5 text-[9px] font-semibold">Watch</button>
                <button type="button" className="h-8 border border-foreground px-2.5 text-[9px] font-semibold">Evidence</button>
              </div>
            </aside>
          </section>
        </div>
      </div>
    </Layout>
  );
}

function Legend({ tone, label }: { tone: string; label: string }) {
  return <div className="flex items-center gap-2"><span className={cn("h-2.5 w-2.5 shrink-0", tone)} /><span>{label}</span></div>;
}

function MapTool({ icon: Icon, label }: { icon: typeof Radius; label: string }) {
  return <button type="button" className="inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-2 text-[9px] font-semibold"><Icon className="h-3 w-3" />{label}</button>;
}

function MapSignal({ className, label }: { className: string; label?: string }) {
  return (
    <div className={cn("absolute h-3.5 w-3.5", className)}>
      <MapPin className="h-3.5 w-3.5 text-background" />
      {label && <div className="absolute left-5 top-0 w-52 border-2 border-foreground bg-card p-2 text-[9px]"><p className="font-semibold">{label}</p><p className="mt-1 text-destructive">PRE-APPROVAL · site plan filed</p></div>}
    </div>
  );
}

function ParcelShape({ className, label, selected, onClick }: { className: string; label: string; selected: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={cn("absolute border-2 border-foreground p-1 text-left text-[8px] font-semibold", className, selected && "ring-2 ring-[#1a63c7]")}>{label}</button>;
}

function ParcelFact({ label, value }: { label: string; value: string }) {
  return <div className="border-b border-border py-2"><p className="text-[9px] font-semibold">{label}</p><p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">{value}</p></div>;
}

