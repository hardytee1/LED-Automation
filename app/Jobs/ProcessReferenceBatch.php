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
            // Call the Python RAG Service
            // Ideally, put the URL in config/services.php or .env
            $ragServiceUrl = config('services.rag.url', 'http://127.0.0.1:8000');
            
            $response = Http::post("{$ragServiceUrl}/ingest", [
                'file_path' => $absolutePath,
                'batch_id' => $this->batch->id,
                'report_id' => $this->batch->report_id,
            ]);

            if ($response->successful()) {
                Log::info("Batch {$this->batch->id} sent to RAG service successfully.");
                // Status remains 'processing' until the Python service updates it via webhook/callback
            } else {
                Log::error("Failed to send batch {$this->batch->id} to RAG service. Status: {$response->status()}, Body: {$response->body()}");
                $this->batch->update([
                    'status' => 'failed',
                    'notes' => 'RAG Service Error: ' . $response->status()
                ]);
            }
        } catch (\Exception $e) {
            Log::error("Exception processing batch {$this->batch->id}: " . $e->getMessage());
            $this->batch->update([
                'status' => 'failed',
                'notes' => 'System Error: ' . $e->getMessage()
            ]);
        }
    }
}
