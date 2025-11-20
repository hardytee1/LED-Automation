<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
use App\Jobs\ProcessReferenceBatch;
use App\Http\Requests\Reports\ReferenceBatchStoreRequest;
use App\Models\ReferenceBatch;
use App\Models\Report;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;

class ReferenceBatchController extends Controller
{
    public function store(ReferenceBatchStoreRequest $request, Report $report): RedirectResponse
    {
        $this->authorizeReport($request->user()->id, $report);

        $file = $request->file('file');
        $path = $file ? $file->store('reference-batches') : null;

        $batch = ReferenceBatch::create([
            'report_id' => $report->id,
            'uploaded_by' => $request->user()->id,
            'source_filename' => $file?->getClientOriginalName() ?? $request->input('source_filename'),
            'storage_path' => $path,
            'total_references' => 0, // Will be updated by Python service
            'processed_references' => 0,
            'status' => 'pending',
            'notes' => $request->validated('notes'),
            'metadata' => $request->validated('metadata'),
            'submitted_at' => now(),
        ]);

        ProcessReferenceBatch::dispatch($batch);

        return back()->with('flash.banner', 'Reference batch queued for parsing');
    }

    public function queue(Request $request, Report $report, ReferenceBatch $referenceBatch): RedirectResponse
    {
        $this->authorizeReport($request->user()->id, $report);

        abort_unless($referenceBatch->report_id === $report->id, 404);

        $referenceBatch->update([
            'status' => 'pending',
            'notes' => null,
        ]);

        ProcessReferenceBatch::dispatch($referenceBatch);

        return back()->with('flash.banner', 'Reference batch queued for parsing');
    }

    protected function authorizeReport(int $userId, Report $report): void
    {
        abort_unless($report->user_id === $userId, 403);
    }
}
