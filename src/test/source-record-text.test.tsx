import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SourceRecordHeading, SourceRecordText } from '@/components/SourceRecordText';

const title = 'Dallas source title including the full hearing application text. '.repeat(80).slice(0, 3857);

describe('Source record text', () => {
  it('keeps short distinct source text inline', () => {
    render(<>
      <SourceRecordHeading title="Commercial hearing" reference="Z-42" fallbackReference="record-1" />
      <SourceRecordText title="Commercial hearing" excerpt="Proposed interior alterations." />
    </>);
    expect(screen.getByRole('heading', { name: 'Commercial hearing' })).toBeVisible();
    expect(screen.getByText('Proposed interior alterations.')).toBeVisible();
    expect(screen.queryByText('Source text')).not.toBeInTheDocument();
  });

  it.each([title, title.slice(0, 500), `${title.slice(0, 500)}...`, `${title.slice(0, 500)}\u2026`])('deduplicates a title or prefix excerpt without losing the full title (%#)', (excerpt) => {
    render(<>
      <SourceRecordHeading title={title} reference="Z-42" fallbackReference="record-1" />
      <SourceRecordText title={title} excerpt={excerpt} />
    </>);
    expect(screen.getByRole('heading', { name: 'Planning record Z-42' })).toBeVisible();
    expect(screen.getAllByText(title)).toHaveLength(1);
    const original = screen.getByText(title);
    expect(original.textContent).toBe(title);
    expect(original).not.toBeVisible();
    const summary = screen.getByText('Source text');
    expect(summary.tagName).toBe('SUMMARY');
    expect(summary.closest('details')).not.toHaveAttribute('open');
    fireEvent.click(summary);
    expect(summary.closest('details')).toHaveAttribute('open');
    expect(original).toBeVisible();
    const text = screen.getByRole('region', { name: 'Full source text' });
    expect(text).toHaveClass('max-h-64', 'overflow-y-auto');
    expect(text).toHaveAttribute('tabindex', '0');
    expect(screen.queryByText('Evidence excerpt')).not.toBeInTheDocument();
    fireEvent.click(summary);
    expect(original).not.toBeVisible();
  });

  it('retains both long source fields verbatim when the excerpt contains different evidence', () => {
    const excerpt = '\n  Separate source evidence.\n'.repeat(50);
    render(<SourceRecordText title={title} excerpt={excerpt} />);
    fireEvent.click(screen.getByText('Source text'));
    const region = screen.getByRole('region', { name: 'Full source text' });
    expect(region.textContent).toContain(title);
    expect(region.textContent).toContain(excerpt);
    expect(screen.getByText('Evidence excerpt')).toBeVisible();
  });

  it('falls back to the record ID when the reference itself is too long', () => {
    render(<SourceRecordHeading title={title} reference={'reference'.repeat(40)} fallbackReference="record-1" />);
    expect(screen.getByRole('heading', { name: 'Planning record record-1' })).toBeVisible();
  });

  it('suppresses short excerpts already contained in the visible title', () => {
    render(<>
      <SourceRecordHeading title="Commercial hearing" fallbackReference="record-1" />
      <SourceRecordText title="Commercial hearing" excerpt="Commercial hearing" />
    </>);
    expect(screen.getAllByText('Commercial hearing')).toHaveLength(1);
    expect(screen.queryByText('Evidence excerpt unavailable.')).not.toBeInTheDocument();
  });
});
