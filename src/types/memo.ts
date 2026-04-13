export interface Memo {
  executiveSummary: string;
  whyThisDeal: string;
  propertyOverview: string;
  marketOverview: string;
  financialSummary: string;
  risksAndMitigants: string;
  valueCreationPlan: string;
  recommendedAction: string;
}

export interface UpdateMemoRequest {
  executiveSummary?: string;
  whyThisDeal?: string;
  propertyOverview?: string;
  marketOverview?: string;
  financialSummary?: string;
  risksAndMitigants?: string;
  valueCreationPlan?: string;
  recommendedAction?: string;
}
