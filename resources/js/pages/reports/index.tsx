import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import AppLayout from '@/layouts/app-layout';
import reports from '@/routes/reports';
import { type BreadcrumbItem } from '@/types';
import { Head, Link } from '@inertiajs/react';

interface ReportListItem {
    id: number;
    name: string;
    slug: string;
    status: string;
    program_name?: string | null;
    last_generated_at?: string | null;
    sections_count: number;
    references_count: number;
    generation_runs_count: number;
}

interface ReportsIndexProps {
    reports: ReportListItem[];
}

const breadcrumbs: BreadcrumbItem[] = [
    { title: 'Reports', href: reports.index().url },
];

const statusClassMap: Record<string, string> = {
    draft: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-900/40 dark:text-neutral-100',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-100',
    completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-100',
    failed: 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-100',
};

const formatDate = (value?: string | null) =>
    value ? new Date(value).toLocaleString() : 'Not generated yet';

export default function ReportsIndex({ reports: reportItems }: ReportsIndexProps) {
    return (
        <AppLayout breadcrumbs={breadcrumbs}>
            <Head title="Reports" />
            <div className="space-y-6 p-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Laporan Evaluasi Diri</h1>
                        <p className="text-sm text-muted-foreground">
                            Track accreditation report generation runs and reference ingestion status.
                        </p>
                    </div>
                    <Button asChild>
                        <Link href={reports.create().url}>New report</Link>
                    </Button>
                </div>

                {reportItems.length === 0 ? (
                    <Card className="border-dashed">
                        <CardHeader>
                            <CardTitle>No reports yet</CardTitle>
                            <CardDescription>
                                Create a report to begin uploading references and triggering the Python automation pipeline.
                            </CardDescription>
                        </CardHeader>
                    </Card>
                ) : (
                    <div className="grid gap-4 lg:grid-cols-2">
                        {reportItems.map((report) => (
                            <Card key={report.id} className="h-full">
                                <CardHeader className="flex-row items-start justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-lg">
                                            <Link
                                                href={reports.show({ report: report.id }).url}
                                                className="hover:underline"
                                            >
                                                {report.name}
                                            </Link>
                                        </CardTitle>
                                        <CardDescription>
                                            {report.program_name ?? 'Program name pending'}
                                        </CardDescription>
                                    </div>
                                    <Badge
                                        className={statusClassMap[report.status] ?? statusClassMap.draft}
                                        variant="outline"
                                    >
                                        {report.status}
                                    </Badge>
                                </CardHeader>
                                <CardContent className="grid gap-3 text-sm">
                                    <div className="flex items-center justify-between">
                                        <span className="text-muted-foreground">Last generated</span>
                                        <span>{formatDate(report.last_generated_at)}</span>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 text-center">
                                        <div className="rounded-lg border p-3">
                                            <div className="text-2xl font-semibold">
                                                {report.sections_count}
                                            </div>
                                            <p className="text-xs text-muted-foreground">Sections</p>
                                        </div>
                                        <div className="rounded-lg border p-3">
                                            <div className="text-2xl font-semibold">
                                                {report.references_count}
                                            </div>
                                            <p className="text-xs text-muted-foreground">References</p>
                                        </div>
                                        <div className="rounded-lg border p-3">
                                            <div className="text-2xl font-semibold">
                                                {report.generation_runs_count}
                                            </div>
                                            <p className="text-xs text-muted-foreground">Runs</p>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}
            </div>
        </AppLayout>
    );
}
