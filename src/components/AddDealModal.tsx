import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const assetTypes = ['Multifamily', 'Retail', 'Industrial', 'Mixed Use'];
const marketOptions = ['Phoenix, AZ', 'Tampa, FL', 'Austin, TX', 'Nashville, TN', 'Charlotte, NC', 'Dallas, TX', 'Denver, CO', 'Atlanta, GA', 'Orlando, FL'];

interface AddDealModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (deal: { name: string; address: string; market: string; assetClass: string; askingPrice: string; source: string }) => void;
}

export function AddDealModal({ open, onOpenChange, onAdd }: AddDealModalProps) {
  const [form, setForm] = useState({ name: '', address: '', market: '', assetClass: '', askingPrice: '', source: '' });

  const update = (key: string, value: string) => setForm(f => ({ ...f, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.market || !form.assetClass) return;
    onAdd(form);
    setForm({ name: '', address: '', market: '', assetClass: '', askingPrice: '', source: '' });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display">Add New Deal</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="deal-name">Deal Name *</Label>
            <Input id="deal-name" placeholder="e.g. Sunrise Apartments" value={form.name} onChange={e => update('name', e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="deal-address">Address</Label>
            <Input id="deal-address" placeholder="123 Main St" value={form.address} onChange={e => update('address', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="deal-asset-type">Asset Type *</Label>
              <Select value={form.assetClass} onValueChange={v => update('assetClass', v)}>
                <SelectTrigger id="deal-asset-type" aria-label="Asset Type"><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {assetTypes.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="deal-market">Market *</Label>
              <Select value={form.market} onValueChange={v => update('market', v)}>
                <SelectTrigger id="deal-market" aria-label="Market"><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {marketOptions.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="deal-price">Asking Price</Label>
              <Input id="deal-price" placeholder="$0" value={form.askingPrice} onChange={e => update('askingPrice', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="deal-source">Source</Label>
              <Input id="deal-source" placeholder="e.g. CBRE" value={form.source} onChange={e => update('source', e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <button type="button" onClick={() => onOpenChange(false)} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-secondary transition-colors">
              Cancel
            </button>
            <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
              Add Deal
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
