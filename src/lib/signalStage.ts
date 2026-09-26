export type FilingStage = "PRE-APPROVAL" | "APPROVED";

export function signalStageFor(type: string): FilingStage {
  const normalized = type.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (["approved", "issued", "final", "completed"].some((value) => normalized.includes(value))) {
    return "APPROVED";
  }
  if (["pre_", "application", "filed", "review", "permit", "zoning"].some((value) => normalized.includes(value))) {
    return "PRE-APPROVAL";
  }
  return "APPROVED";
}
