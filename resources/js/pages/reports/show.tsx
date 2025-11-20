import InputError from '@/components/input-error';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AppLayout from '@/layouts/app-layout';
import reports from '@/routes/reports';
import { type BreadcrumbItem } from '@/types';
import { Head, Link, useForm } from '@inertiajs/react';
import { type FormEvent, useState } from 'react';

interface Section {
    id: number;
    title: string;
    sequence: number;
    status: string;
    content?: string | null;
    tokens_used?: number | null;
}

interface ReferenceBatch {
    id: number;
    source_filename?: string | null;
    status: string;
    total_references: number;
    processed_references: number;
    notes?: string | null;
    submitted_at?: string | null;
    uploaded_by?: { id: number; name: string; email: string } | null;
}

interface GenerationRun {
    id: number;
    status: string;
    automation_job_id?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    summary?: Record<string, unknown> | null;
    error_message?: string | null;
}

interface ReportDetail {
    id: number;
    name: string;
    status: string;
    program_name?: string | null;
    metadata?: Record<string, unknown> | null;
    references_count: number;
    sections: Section[];
    reference_batches: ReferenceBatch[];
    generation_runs: GenerationRun[];
}

interface Props {
    report: ReportDetail;
}

const formatDateTime = (value?: string | null) =>
    value ? new Date(value).toLocaleString() : '—';

const statusClass = (status: string) => {
    switch (status) {
        case 'completed':
            return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-100';
        case 'failed':
            return 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-100';
        case 'running':
        case 'pending':
            return 'bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-100';
        default:
            return 'bg-neutral-100 text-neutral-700 dark:bg-neutral-900/40 dark:text-neutral-100';
    }
};

export default function ReportShow({ report }: Props) {
    const breadcrumbs: BreadcrumbItem[] = [
        { title: 'Reports', href: reports.index().url },
        { title: report.name, href: reports.show({ report: report.id }).url },
    ];

    const referenceForm = useForm<{ file: File | null; notes: string }>(
        {
            file: null,
            notes: '',
        }
    );

    const runForm = useForm<{ instructions: string }>({ instructions: '' });
    const queueForm = useForm({});
    const [queueingBatchId, setQueueingBatchId] = useState<number | null>(null);

    const handleReferenceSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        referenceForm.transform((data) => ({
            file: data.file,
            notes: data.notes,
        }));

        referenceForm.post(reports.referenceBatches.store({ report: report.id }).url, {
            forceFormData: true,
            onSuccess: () => referenceForm.reset('file', 'notes'),
        });
    };

    const handleRunSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        runForm.transform((data) => ({
            payload: data.instructions ? { instructions: data.instructions } : null,
        }));

        runForm.post(reports.generationRuns.store({ report: report.id }).url, {
            onSuccess: () => runForm.reset('instructions'),
        });
    };

    const handleQueueBatch = (batchId: number) => {
        if (queueForm.processing) {
            return;
        }

        queueForm.post(
            reports.referenceBatches.queue({ report: report.id, referenceBatch: batchId }).url,
            {
                preserveScroll: true,
                onStart: () => setQueueingBatchId(batchId),
                onFinish: () => setQueueingBatchId(null),
            }
        );
    };

    return (
        <AppLayout breadcrumbs={breadcrumbs}>
            <Head title={report.name} />
            <div className="space-y-6 p-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <p className="text-sm text-muted-foreground uppercase">Laporan evaluasi diri</p>
                        <h1 className="text-3xl font-semibold">{report.name}</h1>
                        <p className="text-sm text-muted-foreground">{report.program_name}</p>
                    </div>
                    <div className="flex items-center gap-3">
                        <Badge className={statusClass(report.status)} variant="outline">
                            {report.status}
                        </Badge>
                        <Button variant="outline" asChild>
                            <Link href={reports.index().url}>Back to list</Link>
                        </Button>
                    </div>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                    <Card>
                        <CardHeader>
                            <CardTitle>References</CardTitle>
                            <CardDescription>Total references processed</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-semibold">{report.references_count}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardHeader>
                            <CardTitle>Sections</CardTitle>
                            <CardDescription>Chapters tracked for automation</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-semibold">{report.sections.length}</div>
                        </CardContent>
                    </Card>
                </div>

                <div className="grid gap-4 lg:grid-cols-3">
                    <Card className="lg:col-span-2">
                        <CardHeader>
                            <CardTitle>Sections</CardTitle>
                            <CardDescription>Live preview of automation progress per chapter</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {report.sections.length === 0 && (
                                    <p className="text-sm text-muted-foreground">No sections yet.</p>
                                )}
                                {report.sections.map((section) => (
                                    <div
                                        key={section.id}
                                        className="rounded-lg border p-4"
                                    >
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                            <div>
                                                <p className="text-xs text-muted-foreground">Section {section.sequence}</p>
                                                <p className="text-lg font-semibold">{section.title}</p>
                                            </div>
                                            <Badge className={statusClass(section.status)} variant="outline">
                                                {section.status}
                                            </Badge>
                                        </div>
                                        {section.content && (
                                            <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">
                                                {section.content}
                                            </p>
                                        )}
                                        {section.tokens_used && (
                                            <p className="mt-2 text-xs text-muted-foreground">
                                                Tokens: {section.tokens_used}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Upload references</CardTitle>
                            <CardDescription>Send files for chunking & embeddings</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form className="space-y-4" onSubmit={handleReferenceSubmit}>
                                <div className="space-y-2">
                                    <Label htmlFor="reference-file">Reference file (ZIP)</Label>
                                    <Input
                                        id="reference-file"
                                        type="file"
                                        accept=".zip"
                                        onChange={(event) =>
                                            referenceForm.setData('file', event.currentTarget.files?.[0] ?? null)
                                        }
                                    />
                                    <InputError message={referenceForm.errors.file} />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="reference-notes">Notes</Label>
                                    <textarea
                                        id="reference-notes"
                                        className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={referenceForm.data.notes}
                                        onChange={(event) =>
                                            referenceForm.setData('notes', event.target.value)
                                        }
                                        placeholder="Optional context for the Python worker"
                                    />
                                    <InputError message={referenceForm.errors.notes} />
                                </div>

                                <Button type="submit" disabled={referenceForm.processing} className="w-full">
                                    Queue batch
                                </Button>
                            </form>
                        </CardContent>
                    </Card>
                </div>

                <div className="grid gap-4 lg:grid-cols-3">
                    <Card className="lg:col-span-2">
                        <CardHeader>
                            <CardTitle>Reference batches</CardTitle>
                            <CardDescription>Uploads awaiting chunking & embeddings</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {report.reference_batches.length === 0 && (
                                    <p className="text-sm text-muted-foreground">No uploads yet.</p>
                                )}
                                {report.reference_batches.map((batch) => {
                                    const isActive = ['pending', 'processing'].includes(batch.status);
                                    const isQueueing = queueForm.processing && queueingBatchId === batch.id;

                                    return (
                                        <div key={batch.id} className="rounded-lg border p-4">
                                            <div className="flex flex-wrap items-center justify-between gap-3">
                                                <div>
                                                    <p className="font-semibold">{batch.source_filename ?? 'Batch #' + batch.id}</p>
                                                    <p className="text-xs text-muted-foreground">
                                                        Submitted {formatDateTime(batch.submitted_at)} by{' '}
                                                        {batch.uploaded_by?.name ?? 'Unknown'}
                                                    </p>
                                                </div>
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <Badge className={statusClass(batch.status)} variant="outline">
                                                        {batch.status}
                                                    </Badge>
                                                    {!isActive && (
                                                        <Button
                                                            type="button"
                                                            size="sm"
                                                            variant="outline"
                                                            disabled={isQueueing}
                                                            onClick={() => handleQueueBatch(batch.id)}
                                                        >
                                                            {isQueueing ? 'Queueing…' : 'Queue batch'}
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                        <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                                            <div className="rounded-md bg-muted/40 p-2 text-center">
                                                <p className="text-xl font-semibold">{batch.total_references}</p>
                                                <p className="text-xs text-muted-foreground">Total Found</p>
                                            </div>
                                            <div className="rounded-md bg-muted/40 p-2 text-center">
                                                <p className="text-xl font-semibold">{batch.processed_references}</p>
                                                <p className="text-xs text-muted-foreground">Processed</p>
                                            </div>
                                        </div>
                                            {batch.notes && (
                                                <p className="mt-2 text-sm text-muted-foreground">{batch.notes}</p>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Trigger generation</CardTitle>
                            <CardDescription>Send instructions to FastAPI worker</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form className="space-y-3" onSubmit={handleRunSubmit}>
                                <div className="space-y-2">
                                    <Label htmlFor="instructions">Additional instructions</Label>
                                    <textarea
                                        id="instructions"
                                        className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={runForm.data.instructions}
                                        onChange={(event) =>
                                            runForm.setData('instructions', event.target.value)
                                        }
                                        placeholder="Scope, rubric changes, or manual overrides"
                                    />
                                </div>
                                <Button type="submit" disabled={runForm.processing} className="w-full">
                                    Start run
                                </Button>
                            </form>
                        </CardContent>
                    </Card>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Generation history</CardTitle>
                        <CardDescription>Latest hand-offs to the Python service</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {report.generation_runs.length === 0 && (
                                <p className="text-sm text-muted-foreground">No generation attempts yet.</p>
                            )}
                            {report.generation_runs.map((run) => (
                                <div key={run.id} className="rounded-lg border p-4">
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                        <div>
                                            <p className="font-semibold">Run #{run.id}</p>
                                            <p className="text-xs text-muted-foreground">
                                                Started {formatDateTime(run.started_at)} • Finished {formatDateTime(run.finished_at)}
                                            </p>
                                        </div>
                                        <Badge className={statusClass(run.status)} variant="outline">
                                            {run.status}
                                        </Badge>
                                    </div>
                                    {run.error_message && (
                                        <p className="mt-2 text-sm text-destructive">{run.error_message}</p>
                                    )}
                                    {run.summary && (
                                        <pre className="mt-2 overflow-x-auto rounded-md bg-muted/40 p-3 text-xs">
                                            {JSON.stringify(run.summary, null, 2)}
                                        </pre>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </AppLayout>
    );
}
