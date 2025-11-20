import InputError from '@/components/input-error';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AppLayout from '@/layouts/app-layout';
import reports from '@/routes/reports';
import { type BreadcrumbItem } from '@/types';
import { Head, Link, useForm } from '@inertiajs/react';
import { type FormEvent } from 'react';

interface FormData {
    name: string;
    program_name: string;
}

const breadcrumbs: BreadcrumbItem[] = [
    { title: 'Reports', href: reports.index().url },
    { title: 'Create report', href: reports.create().url },
];

export default function ReportCreate() {
    const form = useForm<FormData>({
        name: '',
        program_name: '',
    });

    const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        form.post(reports.store().url, {
            onSuccess: () => form.reset('name', 'program_name'),
        });
    };

    return (
        <AppLayout breadcrumbs={breadcrumbs}>
            <Head title="Create report" />
            <div className="space-y-6 p-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-semibold">New report</h1>
                        <p className="text-sm text-muted-foreground">
                            Describe the accreditation program you want to generate automatically.
                        </p>
                    </div>
                    <Button variant="ghost" asChild>
                        <Link href={reports.index().url}>Cancel</Link>
                    </Button>
                </div>

                <form className="space-y-6" onSubmit={handleSubmit}>
                    <div className="space-y-2">
                        <Label htmlFor="name">Report name</Label>
                        <Input
                            id="name"
                            value={form.data.name}
                            onChange={(e) => form.setData('name', e.target.value)}
                            required
                            placeholder="LEd 2025 Fakultas Teknik"
                        />
                        <InputError message={form.errors.name} />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="program_name">Program / study major</Label>
                        <Input
                            id="program_name"
                            value={form.data.program_name}
                            onChange={(e) => form.setData('program_name', e.target.value)}
                            placeholder="Teknik Informatika S1"
                        />
                        <InputError message={form.errors.program_name} />
                    </div>

                    <div className="flex gap-3">
                        <Button type="submit" disabled={form.processing}>
                            Create report
                        </Button>
                        {form.recentlySuccessful && (
                            <p className="text-sm text-muted-foreground">Saved</p>
                        )}
                    </div>
                </form>
            </div>
        </AppLayout>
    );
}
