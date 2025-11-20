<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
use App\Http\Requests\Reports\GenerationRunStoreRequest;
use App\Models\GenerationRun;
use App\Models\Report;
use Illuminate\Http\RedirectResponse;

class GenerationRunController extends Controller
{
    public function store(GenerationRunStoreRequest $request, Report $report): RedirectResponse
    {
        $this->authorizeReport($request->user()->id, $report);

        GenerationRun::create([
            'report_id' => $report->id,
            'triggered_by' => $request->user()->id,
            'status' => 'pending',
            'automation_job_id' => null,
            'summary' => null,
            'payload' => $request->validated('payload'),
        ]);

        // Placeholder for dispatching FastAPI orchestration job.

        return back()->with('flash.banner', 'Generation run started');
    }

    protected function authorizeReport(int $userId, Report $report): void
    {
        abort_unless($report->user_id === $userId, 403);
    }
}
