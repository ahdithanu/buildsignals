import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Archive } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import type { AcquisitionCriteria } from './CreateAcquisitionCriteria';

export function RetireAcquisitionCriteria({ box, disabled = false, onRetired, returnFocusRef }: {
  box: { id: string; acquisition_criteria: AcquisitionCriteria };
  disabled?: boolean;
  onRetired: (id: string) => void;
  returnFocusRef?: RefObject<HTMLSelectElement>;
}) {
  const { organizationId, user, role, isDemo } = useAuth();
  const cache = useQueryClient();
  const [open, setOpen] = useState(false);
  const [baseline, setBaseline] = useState(box.acquisition_criteria);
  const mounted = useRef(true);
  const succeeded = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const retire = useMutation({
    mutationFn: () => apiClient.post(`/buy-box/${box.id}/retire`, { expected_criteria: baseline }),
    onSuccess: async () => {
      succeeded.current = true;
      const key = ['saved-acquisition-criteria', organizationId, user?.id];
      await cache.cancelQueries({ queryKey: key });
      await cache.cancelQueries({ queryKey: ['acquisition-screen', organizationId, user?.id] });
      if (mounted.current && document.activeElement === trigger.current) {
        returnFocusRef?.current?.focus();
      }
      cache.setQueryData<Array<{ id: string }>>(key, old => old?.filter(item => item.id !== box.id));
      void cache.invalidateQueries({ queryKey: key });
      void cache.resetQueries({ queryKey: ['acquisition-screen', organizationId, user?.id] });
      if (mounted.current) { setOpen(false); onRetired(box.id); }
    },
    onError: async error => {
      if ('status' in error && error.status === 409) {
        await cache.cancelQueries({ queryKey: ['acquisition-screen', organizationId, user?.id] });
        void cache.invalidateQueries({ queryKey: ['saved-acquisition-criteria', organizationId, user?.id] });
        void cache.invalidateQueries({ queryKey: ['acquisition-screen', organizationId, user?.id] });
      }
    },
  });
  if (isDemo || (role !== 'admin' && role !== 'editor')) return null;
  const conflict = retire.error && 'status' in retire.error && retire.error.status === 409;
  return <AlertDialog open={open} onOpenChange={next => {
    if (next && !retire.isPending) { retire.reset(); setBaseline({ ...box.acquisition_criteria }); }
    setOpen(next);
  }}>
    <AlertDialogTrigger asChild><button ref={trigger} type="button" disabled={disabled}
      aria-label="Retire selected buy box" title="Retire selected buy box"
      className="ml-2 mt-2 inline-flex items-center justify-center border p-2"><Archive size={16} /></button></AlertDialogTrigger>
    <AlertDialogContent className="w-[calc(100%_-_2rem)]" onCloseAutoFocus={event => {
      if (succeeded.current && returnFocusRef?.current) {
        event.preventDefault(); returnFocusRef.current.focus();
      }
    }}>
      <AlertDialogTitle>Retire selected buy box?</AlertDialogTitle>
      <AlertDialogDescription>Past screening records will be kept.</AlertDialogDescription>
      {retire.isError && <p role="alert" className="text-sm">{conflict
        ? 'Buy box changed. Cancel and review it before retiring.'
        : 'Buy box could not be retired. Try again.'}</p>}
      <AlertDialogFooter>
        <AlertDialogCancel>{retire.isPending ? 'Close' : 'Cancel'}</AlertDialogCancel>
        <button type="button" disabled={retire.isPending || !!conflict}
          className="border bg-primary px-4 py-2 text-primary-foreground"
          onClick={() => retire.mutate()}>{retire.isPending ? 'Retiring...' : 'Retire buy box'}</button>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
}
