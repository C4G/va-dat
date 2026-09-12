import { getSession } from '@/lib/auth';
import { Metadata } from 'next';
import { redirect } from 'next/navigation';

export const metadata: Metadata = {
  title: 'Dashboard',
  description: 'Your dashboard',
};

export default async function DashboardPage() {
  const session = await getSession();

  if (!session?.user) {
    redirect('/');
  }

  redirect(session.user.role === 'ADMIN' ? '/admin/models' : '/audit');
}
