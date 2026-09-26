import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { BuildSignalsLogo } from '@/components/BuildSignalsLogo';

interface AuthPageShellProps {
  eyebrow: string;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthPageShell({
  eyebrow,
  title,
  description,
  children,
  footer,
}: AuthPageShellProps) {
  return (
    <main className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex h-14 items-center border-b-2 border-foreground px-5 sm:px-8">
        <BuildSignalsLogo />
        <Link to="/login" className="ml-auto text-[10px] font-semibold hover:underline">
          Sign in
        </Link>
      </header>
      <section className="flex flex-1 items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <p className="section-label">{eyebrow}</p>
          <h1 className="mt-3 text-2xl font-semibold">{title}</h1>
          {description && <p className="mt-2 text-xs leading-5 text-muted-foreground">{description}</p>}
          <div className="mt-8 border-t-2 border-foreground pt-6">{children}</div>
          {footer && <div className="mt-6 text-center text-xs text-muted-foreground">{footer}</div>}
        </div>
      </section>
      <footer className="border-t px-5 py-4 text-[10px] text-muted-foreground sm:px-8">
        BuildSignals · organization-scoped access · evidence-backed intelligence
      </footer>
    </main>
  );
}
