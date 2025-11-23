<?php

namespace App\Jobs;

use App\Models\Report;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class RetrieveReportOutput implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public function __construct(
        public Report $report,
        public string $type,
        public string $jobKey,
        public array $metadata = []
    ) {
        $connection = config('queue.report_outputs_connection', config('queue.default'));
        $queueName = config('queue.report_outputs_queue', 'report-outputs');

        $this->onConnection($connection)->onQueue($queueName);
    }

    public function handle(): void
    {
        $report = $this->report->fresh();
        if (!$report) {
            return;
        }

        try {
            $service = config('services.automation', []);
            $baseUrl = rtrim((string) data_get($service, 'url', ''), '/');

            if (empty($baseUrl)) {
                throw new \RuntimeException('Automation service URL is not configured.');
            }

            $timeout = (int) data_get($service, 'timeout', 120);
            $token = data_get($service, 'token');

            $request = Http::timeout(max($timeout, 30))->acceptJson();
            if (!empty($token)) {
                $request = $request->withToken($token);
            }

            $response = $request->post(
                sprintf('%s/reports/%s/outputs/%s', $baseUrl, $report->uuid, $this->type),
                [
                    'job_key' => $this->jobKey,
                    'report_id' => $report->id,
                    'user_id' => $report->user_id,
                    'metadata' => $this->metadata,
                ],
            );

            if ($response->failed()) {
                $this->markReport($report, [
                    'status' => 'failed',
                    'error' => sprintf('Automation service error (%s): %s', $response->status(), $response->body()),
                ]);

                Log::error('Automation service returned an error for report output.', [
                    'report_id' => $report->id,
                    'type' => $this->type,
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);

                return;
            }

            $responsePayload = $response->json();
            $outputPayload = Arr::get($responsePayload, 'payload', $responsePayload);

            $this->markReport($report, [
                'status' => Arr::get($responsePayload, 'status', 'completed'),
                'payload' => $outputPayload,
                'meta' => Arr::get($responsePayload, 'meta'),
            ]);
        } catch (\Throwable $throwable) {
            Log::error('Failed retrieving automation output.', [
                'report_id' => $report->id,
                'type' => $this->type,
                'message' => $throwable->getMessage(),
            ]);

            $this->markReport($report, [
                'status' => 'failed',
                'error' => $throwable->getMessage(),
            ]);

            throw $throwable;
        }
    }

    protected function markReport(Report $report, array $data): void
    {
        $column = $this->type === 'penetapan' ? 'penetapan_json' : 'pelaksanaan_json';
        $existing = (array) ($report->{$column} ?? []);

        $snapshot = array_filter([
            'requested_by' => $data['requested_by'] ?? ($existing['requested_by'] ?? null),
            'status' => $data['status'] ?? ($existing['status'] ?? null),
            'payload' => $data['payload'] ?? ($existing['payload'] ?? null),
            'meta' => $data['meta'] ?? ($existing['meta'] ?? null),
            'error' => $data['error'] ?? null,
            'job_key' => $this->jobKey,
            'updated_at' => now()->toISOString(),
        ], fn ($value) => $value !== null && $value !== []);

        $report->forceFill([
            $column => $snapshot,
        ])->save();
    }
}
