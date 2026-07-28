const STATE_NAME_TO_CODE: Record<string, string> = {
  alabama: 'AL',
  alaska: 'AK',
  arizona: 'AZ',
  arkansas: 'AR',
  california: 'CA',
  colorado: 'CO',
  connecticut: 'CT',
  delaware: 'DE',
  florida: 'FL',
  georgia: 'GA',
  hawaii: 'HI',
  idaho: 'ID',
  illinois: 'IL',
  indiana: 'IN',
  iowa: 'IA',
  kansas: 'KS',
  kentucky: 'KY',
  louisiana: 'LA',
  maine: 'ME',
  maryland: 'MD',
  massachusetts: 'MA',
  michigan: 'MI',
  minnesota: 'MN',
  mississippi: 'MS',
  missouri: 'MO',
  montana: 'MT',
  nebraska: 'NE',
  nevada: 'NV',
  'new hampshire': 'NH',
  'new jersey': 'NJ',
  'new mexico': 'NM',
  'new york': 'NY',
  'north carolina': 'NC',
  'north dakota': 'ND',
  ohio: 'OH',
  oklahoma: 'OK',
  oregon: 'OR',
  pennsylvania: 'PA',
  'rhode island': 'RI',
  'south carolina': 'SC',
  'south dakota': 'SD',
  tennessee: 'TN',
  texas: 'TX',
  utah: 'UT',
  vermont: 'VT',
  virginia: 'VA',
  washington: 'WA',
  'washington state': 'WA',
  'west virginia': 'WV',
  wisconsin: 'WI',
  wyoming: 'WY',
};

export function stateCodeFromJurisdiction(jurisdiction?: string | null) {
  if (!jurisdiction) return null;
  const trimmed = jurisdiction.trim();
  const suffix = trimmed.match(/,\s*([A-Z]{2})$/);
  if (suffix) return suffix[1];
  if (trimmed.length === 2 && /^[A-Z]{2}$/.test(trimmed)) return trimmed;
  return STATE_NAME_TO_CODE[trimmed.toLowerCase()] ?? null;
}

export function sourceHealthHref(jurisdiction?: string | null) {
  const state = stateCodeFromJurisdiction(jurisdiction);
  return state ? `/source-health?state=${state}` : '/source-health';
}
