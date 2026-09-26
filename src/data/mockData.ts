export interface Deal {
  id: string;
  name: string;
  address: string;
  market: string;
  assetClass: string;
  askingPrice: number;
  noi: number;
  dealScore: number;
  projectedIrr: number;
  equityMultiple: number;
  riskLevel: 'low' | 'medium' | 'high';
  status: 'new' | 'qualified' | 'underwriting' | 'ic-review' | 'loi-sent' | 'psa' | 'closing' | 'dead';
  source: string;
  broker: string;
  yearBuilt: number;
  units: number;
  squareFeet: number;
  summary: string;
  thesis: string;
  risks: string[];
  riskFlags: string[];
  nextSteps: string[];
  signals: Signal[];
  documents: Document[];
  assumptions: Assumptions;
  memo: Memo;
  activity: Activity[];
  lastUpdated: string;
  dueDate: string;
  owner: string;
  cashOnCash: number;
  subscores: {
    marketAttractiveness: number;
    financialUpside: number;
    operationalComplexity: number;
    permittingRisk: number;
    executionSpeed: number;
  };
}

export interface Signal {
  id: string;
  type: 'zoning' | 'permit' | 'listing' | 'ownership' | 'competitor' | 'demographic';
  property: string;
  summary: string;
  confidence: 'high' | 'medium' | 'low';
  date: string;
  impact: 'positive' | 'negative' | 'neutral';
}

export interface Document {
  name: string;
  type: string;
  date: string;
}

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

export interface Activity {
  id: string;
  type: 'note' | 'status' | 'comment' | 'enrichment' | 'score';
  content: string;
  user: string;
  date: string;
}

const markets = ['Phoenix, AZ', 'Tampa, FL', 'Austin, TX', 'Nashville, TN', 'Charlotte, NC', 'Dallas, TX', 'Denver, CO', 'Atlanta, GA', 'Raleigh, NC', 'Orlando, FL'];
const sources = ['Broker', 'Off-market', 'Auction', 'Direct mail', 'CoStar', 'Referral'];
const owners = ['Sarah Chen', 'Marcus Reid', 'Elena Voss', 'James Park'];

export const deals: Deal[] = [
  {
    id: '1',
    name: 'Sunset Villas',
    address: '4820 W Sunset Blvd, Phoenix, AZ 85043',
    market: 'Phoenix, AZ',
    assetClass: 'Multifamily',
    askingPrice: 12500000,
    noi: 875000,
    dealScore: 87,
    projectedIrr: 18.4,
    equityMultiple: 2.1,
    riskLevel: 'low',
    status: 'underwriting',
    source: 'Broker',
    broker: 'CBRE - Mike Johnson',
    yearBuilt: 2004,
    units: 96,
    squareFeet: 82000,
    summary: 'Well-maintained 96-unit garden-style multifamily complex in a high-growth Phoenix submarket. Strong rent growth fundamentals with below-market rents offering immediate value-add upside. Recent infrastructure investments in the corridor are accelerating demand.',
    thesis: 'Acquire at a 7.0% cap rate with 15-20% below-market rents. Execute a $8K/unit renovation program to achieve $200/unit rent premiums within 18 months. Exit at a 5.75% cap rate after stabilization.',
    risks: ['Construction cost overruns on renovation', 'Phoenix supply pipeline may compress cap rates', 'Interest rate environment could affect exit pricing'],
    riskFlags: ['Below market rents', 'High capex'],
    nextSteps: ['Complete property inspection', 'Finalize renovation scope', 'Submit LOI by March 15'],
    signals: [],
    documents: [
      { name: 'Offering Memorandum', type: 'PDF', date: '2024-02-10' },
      { name: 'Rent Roll - Jan 2024', type: 'Excel', date: '2024-02-08' },
      { name: 'T12 Operating Statement', type: 'PDF', date: '2024-02-08' },
      { name: 'Phase I ESA', type: 'PDF', date: '2024-01-20' },
      { name: 'Property Photos', type: 'ZIP', date: '2024-02-05' },
    ],
    assumptions: {
      purchasePrice: 12500000,
      closingCosts: 375000,
      renovationCost: 768000,
      exitCapRate: 5.75,
      holdPeriod: 5,
      rentGrowth: 3.5,
      vacancy: 6,
      opexRatio: 42,
      ltv: 65,
      interestRate: 5.25,
      stabilizationMonths: 18,
    },
    memo: {
      executiveSummary: 'Sunset Villas presents a compelling value-add multifamily acquisition in the high-growth Phoenix market. The property offers immediate upside through below-market rents and a proven renovation playbook.',
      whyThisDeal: 'Below-market rents with strong submarket fundamentals. Phoenix continues to attract population and job growth, driving sustained rental demand.',
      propertyOverview: '96-unit garden-style community built in 2004. Mix of 1BR/2BR/3BR units. Amenities include pool, fitness center, and covered parking.',
      marketOverview: 'Phoenix multifamily market continues to outperform with 4.2% rent growth YoY and vacancy below 5%. The West Valley corridor is benefiting from $2B+ in infrastructure investment.',
      financialSummary: 'Projected 18.4% levered IRR and 2.1x equity multiple over a 5-year hold. Year 1 cash-on-cash of 7.2% growing to 9.1% at stabilization.',
      risksAndMitigants: 'Supply risk mitigated by submarket barriers to entry. Renovation cost risk managed through fixed-price GC contract. Rate risk hedged with rate cap.',
      valueCreationPlan: 'Interior renovations ($8K/unit), exterior improvements, operational efficiencies through new management platform. Target $200/unit rent premiums.',
      recommendedAction: 'Proceed to LOI at $12.25M. Negotiate 60-day due diligence with two 15-day extensions.',
    },
    activity: [
      { id: 'a1', type: 'enrichment', content: 'AI enrichment completed — market score updated to 87', user: 'Deal Engine', date: '2024-03-01' },
      { id: 'a2', type: 'status', content: 'Moved to Underwriting', user: 'Sarah Chen', date: '2024-02-28' },
      { id: 'a3', type: 'note', content: 'Toured property. Units 12-24 have updated kitchens. Rest need renovation.', user: 'Marcus Reid', date: '2024-02-25' },
      { id: 'a4', type: 'comment', content: 'Broker confirmed seller motivated. Targeting close by Q2.', user: 'Sarah Chen', date: '2024-02-20' },
    ],
    lastUpdated: '2024-03-01',
    dueDate: '2024-03-15',
    owner: 'Sarah Chen',
    cashOnCash: 7.2,
    subscores: { marketAttractiveness: 91, financialUpside: 85, operationalComplexity: 78, permittingRisk: 92, executionSpeed: 88 },
  },
  {
    id: '2',
    name: 'Mesa Grove Apartments',
    address: '1150 E Mesa Dr, Mesa, AZ 85203',
    market: 'Phoenix, AZ',
    assetClass: 'Multifamily',
    askingPrice: 8200000,
    noi: 615000,
    dealScore: 79,
    projectedIrr: 15.8,
    equityMultiple: 1.9,
    riskLevel: 'medium',
    status: 'qualified',
    source: 'Off-market',
    broker: 'Direct - Owner',
    yearBuilt: 1998,
    units: 64,
    squareFeet: 54000,
    summary: 'Off-market 64-unit multifamily in Mesa with deferred maintenance creating value-add opportunity. Current owner self-manages with below-market operations.',
    thesis: 'Acquire off-market at discount to replacement cost. Professional management and targeted renovations to drive 20%+ NOI growth.',
    risks: ['Deferred maintenance scope uncertainty', 'Older vintage may require structural work', 'Mesa submarket faces new supply'],
    riskFlags: ['High capex', 'Permitting complexity'],
    nextSteps: ['Order property condition report', 'Get renovation bids', 'Negotiate purchase price'],
    signals: [],
    documents: [
      { name: 'Rent Roll', type: 'Excel', date: '2024-02-15' },
      { name: 'T12 Statement', type: 'PDF', date: '2024-02-12' },
    ],
    assumptions: { purchasePrice: 8200000, closingCosts: 246000, renovationCost: 640000, exitCapRate: 6.0, holdPeriod: 5, rentGrowth: 3.0, vacancy: 7, opexRatio: 45, ltv: 65, interestRate: 5.5, stabilizationMonths: 24 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [
      { id: 'b1', type: 'status', content: 'Moved to Qualified', user: 'Marcus Reid', date: '2024-02-20' },
      { id: 'b2', type: 'note', content: 'Owner willing to carry paper on 10% of purchase price', user: 'Marcus Reid', date: '2024-02-18' },
    ],
    lastUpdated: '2024-02-20',
    dueDate: '2024-03-10',
    owner: 'Marcus Reid',
    cashOnCash: 6.5,
    subscores: { marketAttractiveness: 82, financialUpside: 78, operationalComplexity: 65, permittingRisk: 75, executionSpeed: 80 },
  },
  {
    id: '3',
    name: 'Riverpoint Retail Center',
    address: '3200 Riverpoint Pkwy, Tampa, FL 33607',
    market: 'Tampa, FL',
    assetClass: 'Retail',
    askingPrice: 6800000,
    noi: 544000,
    dealScore: 72,
    projectedIrr: 14.2,
    equityMultiple: 1.8,
    riskLevel: 'medium',
    status: 'new',
    source: 'CoStar',
    broker: 'JLL - Lisa Park',
    yearBuilt: 2008,
    units: 0,
    squareFeet: 42000,
    summary: 'Neighborhood retail center anchored by national credit tenant with 7 years remaining on lease. Shadow-anchored by Publix. Strong traffic counts and growing demographics.',
    thesis: 'Stable cash flow from credit tenancy with upside from re-leasing smaller suites at higher rents upon rollover.',
    risks: ['Retail headwinds in secondary suites', 'Tampa permitting delays for tenant improvements', 'Insurance cost escalation in Florida'],
    riskFlags: ['Permitting complexity', 'Weak comps'],
    nextSteps: ['Review lease abstracts', 'Analyze tenant sales data', 'Tour property'],
    signals: [],
    documents: [{ name: 'Offering Memorandum', type: 'PDF', date: '2024-02-22' }],
    assumptions: { purchasePrice: 6800000, closingCosts: 204000, renovationCost: 150000, exitCapRate: 6.5, holdPeriod: 7, rentGrowth: 2.5, vacancy: 8, opexRatio: 35, ltv: 60, interestRate: 5.75, stabilizationMonths: 12 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [{ id: 'c1', type: 'status', content: 'Added to pipeline', user: 'Elena Voss', date: '2024-02-22' }],
    lastUpdated: '2024-02-22',
    dueDate: '2024-03-20',
    owner: 'Elena Voss',
    cashOnCash: 6.8,
    subscores: { marketAttractiveness: 74, financialUpside: 70, operationalComplexity: 82, permittingRisk: 58, executionSpeed: 72 },
  },
  {
    id: '4',
    name: 'Oakline Industrial Park',
    address: '8900 Oakline Rd, Dallas, TX 75241',
    market: 'Dallas, TX',
    assetClass: 'Industrial',
    askingPrice: 18500000,
    noi: 1480000,
    dealScore: 91,
    projectedIrr: 21.3,
    equityMultiple: 2.4,
    riskLevel: 'low',
    status: 'ic-review',
    source: 'Broker',
    broker: 'Cushman - Tom Wells',
    yearBuilt: 2015,
    units: 0,
    squareFeet: 185000,
    summary: 'Class A industrial distribution facility in South Dallas logistics corridor. 100% leased to investment-grade tenant with 5-year NNN lease. Below-market rent with 3% annual escalations.',
    thesis: 'Core-plus industrial with embedded rent growth. Mark-to-market at lease expiry provides significant NOI upside. Dallas industrial fundamentals remain strongest in Sun Belt.',
    risks: ['Single tenant concentration', 'E-commerce demand normalization', 'Property tax reassessment risk'],
    riskFlags: [],
    nextSteps: ['Present to IC on March 5', 'Finalize debt terms', 'Complete environmental review'],
    signals: [],
    documents: [
      { name: 'Offering Memorandum', type: 'PDF', date: '2024-01-15' },
      { name: 'Lease Agreement', type: 'PDF', date: '2024-01-20' },
      { name: 'Phase I ESA', type: 'PDF', date: '2024-02-01' },
      { name: 'Survey', type: 'PDF', date: '2024-02-05' },
      { name: 'Title Report', type: 'PDF', date: '2024-02-10' },
    ],
    assumptions: { purchasePrice: 18500000, closingCosts: 555000, renovationCost: 0, exitCapRate: 5.25, holdPeriod: 5, rentGrowth: 3.0, vacancy: 3, opexRatio: 15, ltv: 60, interestRate: 4.85, stabilizationMonths: 0 },
    memo: { executiveSummary: 'Oakline Industrial Park is a core-plus acquisition offering stable NNN cash flows with embedded mark-to-market upside in the nation\'s strongest industrial market.', whyThisDeal: 'Below-market NNN lease with investment-grade tenant in premier logistics corridor.', propertyOverview: '185,000 SF Class A distribution facility built in 2015. 32\' clear height, ESFR sprinklers, 30 dock doors.', marketOverview: 'Dallas-Fort Worth industrial vacancy at 4.2% with 6.8% rent growth YoY. South Dallas corridor benefits from intermodal access and population growth.', financialSummary: 'Projected 21.3% levered IRR and 2.4x equity multiple. Stable 8.0% cash-on-cash yield from day one.', risksAndMitigants: 'Single tenant risk mitigated by investment-grade credit and essential-use facility. Tax risk managed through protest provisions.', valueCreationPlan: 'Hold for NNN cash flow. Mark rents to market at lease expiry for 25%+ NOI growth. Evaluate expansion on adjacent parcel.', recommendedAction: 'Approve at $18.5M. Target 60% LTV agency debt at 4.85%.' },
    activity: [
      { id: 'd1', type: 'status', content: 'Moved to IC Review', user: 'Sarah Chen', date: '2024-02-28' },
      { id: 'd2', type: 'note', content: 'Debt quotes received. Best terms from Freddie at 4.85% fixed.', user: 'James Park', date: '2024-02-26' },
      { id: 'd3', type: 'comment', content: 'Excellent basis relative to replacement cost ($105/SF vs $135/SF new).', user: 'Sarah Chen', date: '2024-02-22' },
    ],
    lastUpdated: '2024-02-28',
    dueDate: '2024-03-05',
    owner: 'Sarah Chen',
    cashOnCash: 8.0,
    subscores: { marketAttractiveness: 95, financialUpside: 92, operationalComplexity: 95, permittingRisk: 90, executionSpeed: 85 },
  },
  {
    id: '5',
    name: 'Juniper Square Lofts',
    address: '220 Juniper St NW, Atlanta, GA 30308',
    market: 'Atlanta, GA',
    assetClass: 'Multifamily',
    askingPrice: 15800000,
    noi: 1027000,
    dealScore: 83,
    projectedIrr: 16.9,
    equityMultiple: 2.0,
    riskLevel: 'low',
    status: 'loi-sent',
    source: 'Referral',
    broker: 'Walker & Dunlop - Amy Lin',
    yearBuilt: 2012,
    units: 120,
    squareFeet: 110000,
    summary: 'Urban loft-style multifamily in Midtown Atlanta. Transit-oriented location with walk score of 92. Strong millennial demographic and employment growth from tech sector expansion.',
    thesis: 'Premium urban asset with organic rent growth driven by Atlanta\'s tech boom. Light touch value-add through amenity upgrades and smart home package.',
    risks: ['Atlanta multifamily supply in Midtown', 'Tech sector slowdown risk', 'Rising insurance premiums'],
    riskFlags: ['Below market rents'],
    nextSteps: ['Negotiate LOI terms', 'Schedule property inspection', 'Order appraisal'],
    signals: [],
    documents: [
      { name: 'Offering Memorandum', type: 'PDF', date: '2024-02-01' },
      { name: 'Rent Roll', type: 'Excel', date: '2024-02-05' },
      { name: 'T12 Statement', type: 'PDF', date: '2024-02-05' },
    ],
    assumptions: { purchasePrice: 15800000, closingCosts: 474000, renovationCost: 480000, exitCapRate: 5.5, holdPeriod: 5, rentGrowth: 3.2, vacancy: 5, opexRatio: 40, ltv: 65, interestRate: 5.1, stabilizationMonths: 12 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [
      { id: 'e1', type: 'status', content: 'LOI submitted at $15.5M', user: 'Elena Voss', date: '2024-03-01' },
      { id: 'e2', type: 'comment', content: 'Broker expecting multiple offers. We are competitive.', user: 'Elena Voss', date: '2024-02-28' },
    ],
    lastUpdated: '2024-03-01',
    dueDate: '2024-03-08',
    owner: 'Elena Voss',
    cashOnCash: 6.5,
    subscores: { marketAttractiveness: 86, financialUpside: 81, operationalComplexity: 85, permittingRisk: 88, executionSpeed: 78 },
  },
  {
    id: '6',
    name: 'Magnolia Mixed-Use',
    address: '1400 Magnolia Ave, Nashville, TN 37212',
    market: 'Nashville, TN',
    assetClass: 'Mixed Use',
    askingPrice: 9200000,
    noi: 690000,
    dealScore: 76,
    projectedIrr: 15.1,
    equityMultiple: 1.85,
    riskLevel: 'medium',
    status: 'qualified',
    source: 'Broker',
    broker: 'Marcus & Millichap - Dave Ruiz',
    yearBuilt: 2016,
    units: 48,
    squareFeet: 58000,
    summary: 'Mixed-use property with 48 residential units over 12,000 SF of ground-floor retail in trendy East Nashville. Strong walkability and lifestyle appeal.',
    thesis: 'Nashville growth story with diversified income streams. Retail component provides downside protection while residential drives upside.',
    risks: ['Nashville tourism sensitivity', 'Mixed-use management complexity', 'Retail lease rollover in Year 3'],
    riskFlags: ['Permitting complexity'],
    nextSteps: ['Analyze retail tenant credit', 'Review condo conversion feasibility', 'Tour property'],
    signals: [],
    documents: [{ name: 'Offering Memorandum', type: 'PDF', date: '2024-02-18' }],
    assumptions: { purchasePrice: 9200000, closingCosts: 276000, renovationCost: 350000, exitCapRate: 5.75, holdPeriod: 5, rentGrowth: 3.0, vacancy: 6, opexRatio: 38, ltv: 65, interestRate: 5.35, stabilizationMonths: 15 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [{ id: 'f1', type: 'status', content: 'Moved to Qualified', user: 'James Park', date: '2024-02-20' }],
    lastUpdated: '2024-02-20',
    dueDate: '2024-03-18',
    owner: 'James Park',
    cashOnCash: 6.1,
    subscores: { marketAttractiveness: 80, financialUpside: 74, operationalComplexity: 70, permittingRisk: 68, executionSpeed: 76 },
  },
  {
    id: '7',
    name: 'Cypress Point Industrial',
    address: '5500 Cypress Point Dr, Austin, TX 78744',
    market: 'Austin, TX',
    assetClass: 'Industrial',
    askingPrice: 7400000,
    noi: 555000,
    dealScore: 81,
    projectedIrr: 16.5,
    equityMultiple: 1.95,
    riskLevel: 'low',
    status: 'underwriting',
    source: 'Off-market',
    broker: 'Direct - Owner',
    yearBuilt: 2010,
    units: 0,
    squareFeet: 65000,
    summary: 'Last-mile distribution facility in Southeast Austin tech corridor. Multi-tenant flex industrial with 95% occupancy and diverse tenant base.',
    thesis: 'Irreplaceable infill location with strong rent growth from Austin\'s expanding logistics needs. Multi-tenant diversification reduces risk.',
    risks: ['Austin property tax burden', 'Flex industrial may face functional obsolescence', 'Tenant rollover concentration in Year 2'],
    riskFlags: [],
    nextSteps: ['Complete underwriting model', 'Get updated rent comps', 'Schedule tenant interviews'],
    signals: [],
    documents: [
      { name: 'Rent Roll', type: 'Excel', date: '2024-02-20' },
      { name: 'T12 Statement', type: 'PDF', date: '2024-02-20' },
      { name: 'Survey', type: 'PDF', date: '2024-02-15' },
    ],
    assumptions: { purchasePrice: 7400000, closingCosts: 222000, renovationCost: 200000, exitCapRate: 5.5, holdPeriod: 5, rentGrowth: 3.5, vacancy: 5, opexRatio: 22, ltv: 60, interestRate: 5.0, stabilizationMonths: 6 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [{ id: 'g1', type: 'status', content: 'Moved to Underwriting', user: 'Marcus Reid', date: '2024-02-22' }],
    lastUpdated: '2024-02-22',
    dueDate: '2024-03-12',
    owner: 'Marcus Reid',
    cashOnCash: 7.5,
    subscores: { marketAttractiveness: 84, financialUpside: 80, operationalComplexity: 88, permittingRisk: 82, executionSpeed: 78 },
  },
  {
    id: '8',
    name: 'Harbor Walk Retail',
    address: '900 Harbor Walk, Charlotte, NC 28202',
    market: 'Charlotte, NC',
    assetClass: 'Retail',
    askingPrice: 4200000,
    noi: 336000,
    dealScore: 68,
    projectedIrr: 13.1,
    equityMultiple: 1.7,
    riskLevel: 'high',
    status: 'new',
    source: 'Auction',
    broker: 'Ten-X',
    yearBuilt: 2001,
    units: 0,
    squareFeet: 28000,
    summary: 'Strip retail center in South End Charlotte. 75% occupied with near-term lease expirations. Upside through re-tenanting and rent growth in rapidly gentrifying submarket.',
    thesis: 'Deep value play in path of growth. Re-tenant vacant suites and mark existing leases to market upon rollover.',
    risks: ['High vacancy risk during re-leasing', 'Construction disruption from adjacent development', 'Capital intensive TI requirements'],
    riskFlags: ['Weak comps', 'High capex', 'Title issue risk'],
    nextSteps: ['Bid on auction platform', 'Analyze tenant prospects', 'Get construction impact assessment'],
    signals: [],
    documents: [{ name: 'Auction Package', type: 'PDF', date: '2024-02-25' }],
    assumptions: { purchasePrice: 4200000, closingCosts: 126000, renovationCost: 500000, exitCapRate: 6.25, holdPeriod: 5, rentGrowth: 2.0, vacancy: 12, opexRatio: 30, ltv: 55, interestRate: 6.0, stabilizationMonths: 24 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [{ id: 'h1', type: 'status', content: 'Added from auction listing', user: 'James Park', date: '2024-02-25' }],
    lastUpdated: '2024-02-25',
    dueDate: '2024-03-05',
    owner: 'James Park',
    cashOnCash: 5.2,
    subscores: { marketAttractiveness: 72, financialUpside: 68, operationalComplexity: 55, permittingRisk: 60, executionSpeed: 65 },
  },
  {
    id: '9',
    name: 'Ridgeline Apartments',
    address: '3400 Ridgeline Rd, Denver, CO 80239',
    market: 'Denver, CO',
    assetClass: 'Multifamily',
    askingPrice: 22000000,
    noi: 1540000,
    dealScore: 85,
    projectedIrr: 17.6,
    equityMultiple: 2.15,
    riskLevel: 'low',
    status: 'psa',
    source: 'Broker',
    broker: 'Newmark - John Stevens',
    yearBuilt: 2017,
    units: 156,
    squareFeet: 142000,
    summary: 'Newer vintage 156-unit multifamily in Northeast Denver near airport corridor. Strong occupancy with institutional quality construction and amenity package.',
    thesis: 'Core-plus acquisition with organic rent growth in undersupplied submarket. Minimal capex required. Long-term appreciation play in Denver\'s growth corridor.',
    risks: ['Denver rent control legislative risk', 'Airport corridor noise concerns', 'Insurance market tightening'],
    riskFlags: [],
    nextSteps: ['Execute PSA', 'Begin due diligence', 'Order appraisal and survey'],
    signals: [],
    documents: [
      { name: 'Purchase & Sale Agreement', type: 'PDF', date: '2024-02-28' },
      { name: 'Offering Memorandum', type: 'PDF', date: '2024-01-10' },
      { name: 'Rent Roll', type: 'Excel', date: '2024-02-20' },
      { name: 'T12 Statement', type: 'PDF', date: '2024-02-20' },
      { name: 'Phase I ESA', type: 'PDF', date: '2024-02-25' },
      { name: 'Property Condition Report', type: 'PDF', date: '2024-02-25' },
    ],
    assumptions: { purchasePrice: 22000000, closingCosts: 660000, renovationCost: 200000, exitCapRate: 5.25, holdPeriod: 5, rentGrowth: 3.2, vacancy: 5, opexRatio: 38, ltv: 65, interestRate: 4.95, stabilizationMonths: 6 },
    memo: { executiveSummary: 'Ridgeline Apartments is a core-plus multifamily opportunity in Denver\'s high-growth airport corridor offering stable cash flow and organic appreciation.', whyThisDeal: 'Institutional quality asset at attractive basis in undersupplied submarket.', propertyOverview: '156-unit community built in 2017 with modern finishes and full amenity package.', marketOverview: 'Denver multifamily fundamentals remain strong with 3.5% rent growth and declining vacancy.', financialSummary: 'Projected 17.6% levered IRR and 2.15x equity multiple over 5-year hold.', risksAndMitigants: 'Legislative risk managed through industry association engagement. Noise mitigated by soundproofing and distance from runways.', valueCreationPlan: 'Light amenity upgrades, operational efficiencies, and organic rent growth. No heavy lift required.', recommendedAction: 'Close at $22M per executed PSA. Target 65% LTV Fannie Mae financing.' },
    activity: [
      { id: 'i1', type: 'status', content: 'PSA executed', user: 'Sarah Chen', date: '2024-02-28' },
      { id: 'i2', type: 'note', content: 'Lender engaged. Targeting 30-day close.', user: 'James Park', date: '2024-02-27' },
    ],
    lastUpdated: '2024-02-28',
    dueDate: '2024-03-30',
    owner: 'Sarah Chen',
    cashOnCash: 7.0,
    subscores: { marketAttractiveness: 88, financialUpside: 84, operationalComplexity: 90, permittingRisk: 85, executionSpeed: 82 },
  },
  {
    id: '10',
    name: 'Palms Gateway Mixed-Use',
    address: '6200 Gateway Blvd, Orlando, FL 32819',
    market: 'Orlando, FL',
    assetClass: 'Mixed Use',
    askingPrice: 11000000,
    noi: 770000,
    dealScore: 74,
    projectedIrr: 14.8,
    equityMultiple: 1.82,
    riskLevel: 'medium',
    status: 'dead',
    source: 'CoStar',
    broker: 'Colliers - Rachel Kim',
    yearBuilt: 2009,
    units: 72,
    squareFeet: 78000,
    summary: 'Mixed-use property near International Drive with 72 residential units and 15,000 SF retail. Tourism-adjacent location with seasonal demand patterns.',
    thesis: 'Orlando population growth and tourism recovery create dual demand drivers. Value-add residential with stable retail anchor.',
    risks: ['Tourism cyclicality', 'Hurricane and flood risk', 'Insurance cost escalation', 'Seasonal vacancy spikes'],
    riskFlags: ['Permitting complexity', 'High capex'],
    nextSteps: ['Deal killed — insurance costs made returns unworkable'],
    signals: [],
    documents: [{ name: 'Offering Memorandum', type: 'PDF', date: '2024-01-30' }],
    assumptions: { purchasePrice: 11000000, closingCosts: 330000, renovationCost: 600000, exitCapRate: 6.0, holdPeriod: 5, rentGrowth: 2.5, vacancy: 9, opexRatio: 42, ltv: 60, interestRate: 5.75, stabilizationMonths: 18 },
    memo: { executiveSummary: '', whyThisDeal: '', propertyOverview: '', marketOverview: '', financialSummary: '', risksAndMitigants: '', valueCreationPlan: '', recommendedAction: '' },
    activity: [
      { id: 'j1', type: 'status', content: 'Deal killed — insurance costs prohibitive', user: 'Elena Voss', date: '2024-02-15' },
      { id: 'j2', type: 'note', content: 'Insurance quotes came in 40% above underwriting. Returns no longer pencil.', user: 'Elena Voss', date: '2024-02-14' },
    ],
    lastUpdated: '2024-02-15',
    dueDate: '',
    owner: 'Elena Voss',
    cashOnCash: 5.0,
    subscores: { marketAttractiveness: 70, financialUpside: 72, operationalComplexity: 65, permittingRisk: 60, executionSpeed: 70 },
  },
];

export const marketSignals: Signal[] = [
  { id: 's1', type: 'zoning', property: 'West Phoenix Corridor', summary: 'City council approved R-4 zoning overlay allowing higher density multifamily development. Expected to drive land values up 15-20% in affected parcels.', confidence: 'high', date: '2024-03-01', impact: 'positive' },
  { id: 's2', type: 'permit', property: 'South Dallas Industrial', summary: '3 new warehouse permits filed totaling 450,000 SF. May indicate increasing supply competition for Oakline Industrial Park.', confidence: 'medium', date: '2024-02-28', impact: 'negative' },
  { id: 's3', type: 'listing', property: 'Midtown Atlanta', summary: 'Two comparable multifamily assets listed within 0.5 miles of Juniper Square Lofts. Asking prices suggest 5.2% cap rates.', confidence: 'high', date: '2024-02-27', impact: 'neutral' },
  { id: 's4', type: 'ownership', property: 'East Nashville', summary: 'Blackstone acquired 200-unit complex two blocks from Magnolia Mixed-Use at $185K/unit, validating our $192K/unit basis.', confidence: 'high', date: '2024-02-25', impact: 'positive' },
  { id: 's5', type: 'competitor', property: 'Tampa Bay Retail', summary: 'Regency Centers announced $50M acquisition program targeting Tampa Bay neighborhood retail. Increased buyer competition expected.', confidence: 'medium', date: '2024-02-24', impact: 'negative' },
  { id: 's6', type: 'demographic', property: 'Denver Metro', summary: 'Census estimates show 2.8% YoY population growth in NE Denver corridor, outpacing metro average by 1.5x. Supports Ridgeline thesis.', confidence: 'high', date: '2024-02-22', impact: 'positive' },
  { id: 's7', type: 'permit', property: 'Austin SE Corridor', summary: 'Amazon filed permits for 250,000 SF fulfillment center 2 miles from Cypress Point Industrial. Strong demand signal for flex industrial.', confidence: 'high', date: '2024-02-20', impact: 'positive' },
  { id: 's8', type: 'zoning', property: 'Charlotte South End', summary: 'Transit-oriented development overlay approved for South End. Harbor Walk Retail parcel now eligible for mixed-use redevelopment up to 8 stories.', confidence: 'high', date: '2024-02-18', impact: 'positive' },
];

export const aiInsights = [
  'Phoenix multifamily opportunities are scoring above average due to rent growth and lower entry basis. Two deals in your pipeline exceed 85 deal score.',
  'Deals in Tampa are showing elevated timeline risk due to permitting delays. Consider adding 3-6 months to stabilization assumptions for Tampa assets.',
  'Retail strip opportunities under $5M are converting faster than industrial in this pipeline. Average days to close: 47 vs 68.',
  'Your portfolio is overweight multifamily at 60% of pipeline value. Consider diversifying into industrial for risk-adjusted returns.',
  'Debt markets are tightening — average spreads widened 25bps this month. Lock rates early on Ridgeline and Oakline transactions.',
];

export const pipelineStages = ['new', 'qualified', 'underwriting', 'ic-review', 'loi-sent', 'psa', 'closing', 'dead'] as const;

export const stageLabels: Record<string, string> = {
  'new': 'New',
  'qualified': 'Qualified',
  'underwriting': 'Underwriting',
  'ic-review': 'IC Review',
  'loi-sent': 'LOI Sent',
  'psa': 'PSA',
  'closing': 'Closing',
  'dead': 'Dead',
};

export function formatCurrency(value: number): string {
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
  return `$${value.toLocaleString()}`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

export function getScoreColor(score: number): string {
  if (score >= 85) return 'text-success';
  if (score >= 70) return 'text-info';
  if (score >= 55) return 'text-warning';
  return 'text-destructive';
}

export function getScoreBg(score: number): string {
  if (score >= 85) return 'bg-success/10 text-success';
  if (score >= 70) return 'bg-info/10 text-info';
  if (score >= 55) return 'bg-warning/10 text-warning';
  return 'bg-destructive/10 text-destructive';
}
