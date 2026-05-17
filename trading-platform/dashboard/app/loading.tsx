import AppShell from '@/components/layout/AppShell';

export default function Loading() {
  return (
    <AppShell><div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" /></div></AppShell>
  );
}
