<?php

namespace App\Http\Controllers\Reports;

use App\Http\Controllers\Controller;
use App\Models\ReferenceBatch;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ReferenceBatchStatusController extends Controller
{
    public function __invoke(Request $request): JsonResponse
    {
        $token = config('services.rag.webhook_token');

        if ($token && ! hash_equals($token, (string) $request->bearerToken())) {
            abort(401, 'Unauthorized');
        }

        $data = $request->validate([
            'batch_id' => ['required', 'integer', 'exists:reference_batches,id'],
            'status' => ['required', 'string', 'in:pending,processing,completed,failed'],
            'details' => ['nullable', 'array'],
        ]);

        $batch = ReferenceBatch::findOrFail($data['batch_id']);

        $updates = [
            'status' => $data['status'],
        ];

        $details = $data['details'] ?? [];

        if ($data['status'] === 'completed') {
            $chunkCount = (int) ($details['chunks'] ?? 0);
            if ($chunkCount > 0) {
                $updates['total_references'] = $chunkCount;
                $updates['processed_references'] = $chunkCount;
            }
            $updates['notes'] = null;
        }

        if ($data['status'] === 'failed') {
            $updates['notes'] = $details['error'] ?? 'Failed during ingestion';
        }

        $batch->update($updates);

        return response()->json(['status' => 'ok']);
    }
}
