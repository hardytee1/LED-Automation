<?php

namespace App\Jobs;

use App\Models\ReportOutput;
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

    public function __construct(public ReportOutput $output, public string $jobKey)
    {
        $this->onQueue(config('queue.report_outputs_queue', 'report-outputs'));
    }

    public function handle(): void
    {
        $output = $this->output->fresh();
        if (!$output) {
            return;
        }

        $output->loadMissing('report');
        if (!$output->report) {
            $output->update([
                'status' => ReportOutput::STATUS_FAILED,
                'error_message' => 'Report missing for output.',
            ]);
            return;
        }

        $output->update([
            'status' => ReportOutput::STATUS_PROCESSING,
            'started_at' => now(),
        ]);

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
                sprintf('%s/reports/%s/outputs/%s', $baseUrl, $output->report->uuid, $output->type),
                [
                    'job_key' => $this->jobKey,
                    'report_id' => $output->report_id,
                    'user_id' => $output->report->user_id,
                    'metadata' => $output->metadata ?? [],
                ],
            );

            if ($response->failed()) {
                $output->update([
                    'status' => ReportOutput::STATUS_FAILED,
                    'finished_at' => now(),
                    'error_message' => sprintf(
                        'Automation service error (%s): %s',
                        $response->status(),
                        $response->body(),
                    ),
                ]);

                Log::error('Automation service returned an error for report output.', [
                    'output_id' => $output->id,
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);

                return;
            }

            $responsePayload = $response->json();

            $output->update([
                'status' => Arr::get($responsePayload, 'status', ReportOutput::STATUS_COMPLETED),
                'payload' => Arr::get($responsePayload, 'payload'),
                'artifact_path' => Arr::get($responsePayload, 'artifact_path', $output->artifact_path),
                'metadata' => array_filter([
                    ...($output->metadata ?? []),
                    'service_meta' => Arr::get($responsePayload, 'meta'),
                ], fn ($value) => $value !== null),
                'finished_at' => now(),
                'error_message' => null,
            ]);
        } catch (\Throwable $throwable) {
            Log::error('Failed retrieving automation output.', [
                'output_id' => $output->id,
                'message' => $throwable->getMessage(),
            ]);

            $output->update([
                'status' => ReportOutput::STATUS_FAILED,
                'finished_at' => now(),
                'error_message' => $throwable->getMessage(),
            ]);

            throw $throwable;
        }
    }
}
