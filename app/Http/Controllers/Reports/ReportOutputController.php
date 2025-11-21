<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
use App\Jobs\RetrieveReportOutput;
use App\Models\Report;
use App\Models\ReportOutput;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class ReportOutputController extends Controller
{
    public function store(Request $request, Report $report, string $type): JsonResponse
    {
        $this->authorizeReport($request->user()->id, $report);

        $normalizedType = strtolower($type);
        if (!in_array($normalizedType, ReportOutput::supportedTypes(), true)) {
            abort(422, 'Unsupported output type requested.');
        }

        $jobKey = (string) Str::uuid();

        $output = $report->outputs()->create([
            'type' => $normalizedType,
            'status' => ReportOutput::STATUS_QUEUED,
            'job_id' => $jobKey,
            'metadata' => array_filter([
                'requested_by' => $request->user()->only(['id', 'name', 'email']),
                'source' => 'dashboard',
            ]),
        ]);

        RetrieveReportOutput::dispatch($output, $jobKey);

        return response()->json([
            'output' => $output->only([
                'id',
                'type',
                'status',
                'job_id',
                'created_at',
            ]),
        ], 202);
    }

    protected function authorizeReport(int $userId, Report $report): void
    {
        abort_unless($report->user_id === $userId, 403);
    }
}
