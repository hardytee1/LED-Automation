<?php

namespace App\Jobs;

use App\Models\ReferenceBatch;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;

class ProcessReferenceBatch implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public $batch;

    /**
     * Create a new job instance.
     */
    public function __construct(ReferenceBatch $batch)
    {
        $this->batch = $batch;
    }

    /**
     * Execute the job.
     */
    public function handle(): void
    {
        $this->batch->update(['status' => 'processing']);

        // Resolve absolute path using the configured filesystem disk root
        $relativePath = ltrim((string) $this->batch->storage_path, '/');
        $disk = config('filesystems.default', 'local');
        $storage = Storage::disk($disk);
        $absolutePath = method_exists($storage, 'path')
            ? $storage->path($relativePath)
            : storage_path('app/'.$relativePath);

        if (!file_exists($absolutePath)) {
            $this->batch->update([
                'status' => 'failed',
                'notes' => "File not found at path: {$absolutePath}"
            ]);
            Log::error("File not found for batch {$this->batch->id}: {$absolutePath}");
            return;
        }

        try {
            $gpuConfig = config('services.gpu', []);
            $gpuServiceUrl = rtrim((string) data_get($gpuConfig, 'url', config('services.rag.url', 'http://127.0.0.1:8000')), '/');
            $timeout = (int) data_get($gpuConfig, 'timeout', 120);
            $token = data_get($gpuConfig, 'token');

            $request = Http::timeout(max($timeout, 30))->acceptJson();
            if (!empty($token)) {
                $request = $request->withToken($token);
            }

            $payload = [
                'file_path' => $absolutePath,
                'batch_id' => $this->batch->id,
                'report_id' => $this->batch->report_id,
            ];

            $response = $request->post("{$gpuServiceUrl}/ingest", $payload);

            if ($response->failed()) {
                Log::error(
                    'GPU ingest failed for batch {batch} with status {status}: {body}',
                    [
                        'batch' => $this->batch->id,
                        'status' => $response->status(),
                        'body' => $response->body(),
                    ],
                );

                $this->batch->update([
                    'status' => 'failed',
                    'notes' => 'GPU ingest service error: '.$response->status(),
                ]);

                return;
            }

            $chunks = data_get($response->json(), 'chunks');

            $this->batch->update([
                'status' => 'completed',
                'processed_references' => is_numeric($chunks) ? (int) $chunks : $this->batch->processed_references,
                'notes' => is_numeric($chunks)
                    ? sprintf('GPU ingest complete (%d chunks).', (int) $chunks)
                    : 'GPU ingest completed.',
            ]);

            Log::info('Batch {batch} ingested on GPU service.', [
                'batch' => $this->batch->id,
                'report_id' => $this->batch->report_id,
                'chunks' => $chunks,
            ]);
        } catch (\Exception $e) {
            Log::error("Exception processing batch {$this->batch->id}: " . $e->getMessage());
            $this->batch->update([
                'status' => 'failed',
                'notes' => 'System Error: ' . $e->getMessage()
            ]);
        }
    }
}
