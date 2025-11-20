<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
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

        ReferenceBatch::create([
            'report_id' => $report->id,
            'uploaded_by' => $request->user()->id,
            'source_filename' => $file?->getClientOriginalName() ?? $request->input('source_filename'),
            'storage_path' => $path,
            'total_references' => $request->validated('total_references') ?? 0,
            'processed_references' => 0,
            'status' => 'pending',
            'notes' => $request->validated('notes'),
            'metadata' => $request->validated('metadata'),
            'submitted_at' => now(),
        ]);

        return back()->with('flash.banner', 'Reference batch queued for parsing');
    }

    protected function authorizeReport(int $userId, Report $report): void
    {
        abort_unless($report->user_id === $userId, 403);
    }
}
