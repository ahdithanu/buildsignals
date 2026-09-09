import { describe, expect, it } from 'vitest';
import { safeSourceUrl } from '@/lib/sourceUrl';

describe('External parcel evidence URLs', () => {
  it('allows absolute HTTP(S) evidence links', () => {
    expect(safeSourceUrl('https://example.gov/parcel/123')).toBe('https://example.gov/parcel/123');
    expect(safeSourceUrl('http://example.gov/record')).toBe('http://example.gov/record');
  });
  it.each(['javascript:alert(1)', 'data:text/html,test', 'file:///etc/passwd', '/relative', '', null, undefined])('rejects unsafe or missing source %s', value => {
    expect(safeSourceUrl(value)).toBeUndefined();
  });
});
