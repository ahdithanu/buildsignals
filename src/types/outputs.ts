export interface UnderwritingOutputs {
  irr: number;
  equityMultiple: number;
  cashOnCash: number;
  noiGrowth: number;
  requiredEquity: number;
  breakEvenOccupancy: number;
  projections: ProjectionYear[];
  scenarios: ScenarioResult[];
}

export interface ProjectionYear {
  year: number;
  noi: number;
  value: number;
}

export interface ScenarioResult {
  name: string;
  exitCapRate: number;
  rentGrowth: number;
  irr: number;
  equityMultiple: number;
}
