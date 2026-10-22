import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { parcelsApi } from '@/api/parcels';
import { useToast } from '@/hooks/use-toast';
import {
  PARCEL_AVAILABILITY_CSV_TEMPLATE,
  parseParcelAvailabilityCsv,
  type ParsedParcelAvailabilityCsv,
} from '@/lib/parcelAvailabilityImport';

export function ParcelAvailabilityImportPanel({ canManage }: { canManage: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const [parsed, setParsed] = useState<ParsedParcelAvailabilityCsv | null>(null);
  const [fileName, setFileName] = useState<string>();
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<{ imported: number; skipped: number; errors: Array<{ row: number; reason: string }> }>();

  if (!canManage) return null;

  const downloadTemplate = () => {
    const blob = new Blob([PARCEL_AVAILABILITY_CSV_TEMPLATE], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'parcel-availability-template.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleFile = async (file?: File) => {
    if (!file) return;
    const next = parseParcelAvailabilityCsv(await file.text());
    setFileName(file.name);
    setParsed(next);
    setResult(undefined);
  };

  const importRows = async () => {
    if (!parsed || parsed.rows.length === 0) return;
    setIsImporting(true);
    try {
      const next = await parcelsApi.importAvailabilityEvidence(parsed.rows);
      setResult(next);
      toast({
        title: 'Availability intake complete',
        description: `${next.imported} rows imported; ${next.skipped} rows skipped because they failed source-backed matching or validation.`,
        variant: next.skipped ? 'destructive' : 'default',
      });
    } catch {
      toast({
        title: 'Availability intake failed',
        description: 'The batch was not imported. Check the source IDs and try again.',
        variant: 'destructive',
      });
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <section className="rounded-md border bg-card p-4 card-shadow" aria-label="Parcel availability intake">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Parcel Availability Intake</h3>
          <p className="mt-0.5 max-w-3xl text-xs text-muted-foreground">
            Load source-backed listing, broker, owner, or auction evidence in bounded batches. Matching is limited to
            <strong> source_id + external_parcel_id</strong>; addresses are never used to guess parcel identity.
          </p>
        </div>
        <button type="button" className="rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-secondary" onClick={downloadTemplate}>
          Download CSV template
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={(event) => void handleFile(event.target.files?.[0])}
        />
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-md bg-foreground px-3 py-2 text-xs font-semibold text-background"
          onClick={() => inputRef.current?.click()}
        >
          <Upload className="h-3.5 w-3.5" /> Select CSV
        </button>
        {fileName && <span className="text-xs text-muted-foreground">{fileName}</span>}
        {parsed && <span className="text-xs text-muted-foreground">{parsed.rows.length} valid rows · {parsed.errors.length} local errors</span>}
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!parsed?.rows.length || isImporting}
          onClick={() => void importRows()}
        >
          {isImporting ? 'Importing...' : 'Import evidence'}
        </button>
      </div>

      {parsed?.errors.length ? (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" role="alert">
          <p className="font-medium">Rows needing correction</p>
          <ul className="mt-1 list-disc pl-4">
            {parsed.errors.slice(0, 5).map((error) => <li key={`${error.row}-${error.reason}`}>Row {error.row}: {error.reason}</li>)}
          </ul>
          {parsed.errors.length > 5 && <p className="mt-1">+{parsed.errors.length - 5} more rows</p>}
        </div>
      ) : null}

      {result ? (
        <div className="mt-3 rounded-md border bg-secondary/25 px-3 py-2 text-xs" role="status">
          Imported {result.imported} rows; skipped {result.skipped}. Server-side skips require an exact active source and parcel match.
        </div>
      ) : null}
    </section>
  );
}
