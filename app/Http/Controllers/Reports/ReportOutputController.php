<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
use App\Jobs\RetrieveReportOutput;
use App\Models\Report;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class ReportOutputController extends Controller
{
    private const SUPPORTED_TYPES = ['penetapan', 'pelaksanaan'];

    public function store(Request $request, Report $report, string $type): JsonResponse
    {
        $this->authorizeReport($request->user()->id, $report);

        $normalizedType = strtolower($type);
        if (!in_array($normalizedType, self::SUPPORTED_TYPES, true)) {
            abort(422, 'Unsupported output type requested.');
        }

        $jobKey = (string) Str::uuid();
        $metadata = array_filter([
            'requested_by' => $request->user()->only(['id', 'name', 'email']),
            'source' => 'dashboard',
        ]);

        $this->markReportSnapshot($report, $normalizedType, [
            'status' => 'queued',
            'job_key' => $jobKey,
            'requested_by' => $metadata['requested_by'] ?? null,
            'updated_at' => now()->toISOString(),
        ]);

        RetrieveReportOutput::dispatch($report, $normalizedType, $jobKey, $metadata);

        return response()->json([
            'status' => 'queued',
            'job_key' => $jobKey,
            'type' => $normalizedType,
        ], 202);
    }

    protected function markReportSnapshot(Report $report, string $type, array $snapshot): void
    {
        $column = $type === 'penetapan' ? 'penetapan_json' : 'pelaksanaan_json';
        $report->forceFill([
            $column => $snapshot,
        ])->save();
    }

    protected function authorizeReport(int $userId, Report $report): void
    {
        abort_unless($report->user_id === $userId, 403);
    }
}
