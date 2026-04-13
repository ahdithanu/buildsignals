export interface Assumptions {
  purchasePrice: number;
  closingCosts: number;
  renovationCost: number;
  exitCapRate: number;
  holdPeriod: number;
  rentGrowth: number;
  vacancy: number;
  opexRatio: number;
  ltv: number;
  interestRate: number;
  stabilizationMonths: number;
}

export interface UnderwritingOutputs {
  irr: number;
  equityMultiple: number;
  cashOnCash: number;
  noiGrowth: number;
  requiredEquity: number;
  breakEvenOccupancy: number;
}
