<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
use App\Http\Requests\Reports\ReportStoreRequest;
use App\Models\Report;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Inertia;
use Inertia\Response;

class ReportController extends Controller
{
    public function index(Request $request): Response
    {
        $reports = Report::query()
            ->whereBelongsTo($request->user())
            ->withCount(['sections', 'references', 'generationRuns'])
            ->latest()
            ->get()
            ->map(fn (Report $report) => [
                'id' => $report->id,
                'name' => $report->name,
                'slug' => $report->slug,
                'status' => $report->status,
                'program_name' => $report->program_name,
                'last_generated_at' => $report->last_generated_at,
                'sections_count' => $report->sections_count,
                'references_count' => $report->references_count,
                'generation_runs_count' => $report->generation_runs_count,
            ]);

        return Inertia::render('reports/index', [
            'reports' => $reports,
        ]);
    }

    public function create(): Response
    {
        return Inertia::render('reports/create');
    }

    public function store(ReportStoreRequest $request): RedirectResponse
    {
        $data = $request->validated();

        $report = $request->user()->reports()->create([
            'name' => $data['name'],
            'slug' => Str::slug($data['name'].'-'.Str::random(4)),
            'status' => 'draft',
            'program_name' => $data['program_name'] ?? null,
            'metadata' => array_filter([
                ...($data['metadata'] ?? []),
            ]),
        ]);

        return redirect()
            ->route('reports.show', $report)
            ->with('flash.banner', 'Report created');
    }

    public function show(Request $request, Report $report): Response
    {
        $this->authorizeReport($request->user()->id, $report);

        $report->load([
            'sections' => fn ($query) => $query->orderBy('sequence'),
            'referenceBatches.uploadedBy',
            'generationRuns' => fn ($query) => $query->latest(),
        ])->loadCount(['references']);

        return Inertia::render('reports/show', [
            'report' => [
                'id' => $report->id,
                'name' => $report->name,
                'slug' => $report->slug,
                'status' => $report->status,
                'program_name' => $report->program_name,
                'metadata' => $report->metadata,
                'references_count' => $report->references_count,
                'sections' => $report->sections->map(fn ($section) => [
                    'id' => $section->id,
                    'title' => $section->title,
                    'sequence' => $section->sequence,
                    'status' => $section->status,
                    'content' => $section->content,
                    'tokens_used' => $section->tokens_used,
                ]),
                'reference_batches' => $report->referenceBatches->map(fn ($batch) => [
                    'id' => $batch->id,
                    'source_filename' => $batch->source_filename,
                    'status' => $batch->status,
                    'total_references' => $batch->total_references,
                    'processed_references' => $batch->processed_references,
                    'notes' => $batch->notes,
                    'submitted_at' => $batch->submitted_at,
                    'uploaded_by' => $batch->uploadedBy?->only(['id', 'name', 'email']),
                ]),
                'generation_runs' => $report->generationRuns->map(fn ($run) => [
                    'id' => $run->id,
                    'status' => $run->status,
                    'automation_job_id' => $run->automation_job_id,
                    'started_at' => $run->started_at,
                    'finished_at' => $run->finished_at,
                    'summary' => $run->summary,
                    'error_message' => $run->error_message,
                ]),
            ],
        ]);
    }

    protected function authorizeReport(int $userId, Report $report): void
    {
        abort_unless($report->user_id === $userId, 403);
    }
}
