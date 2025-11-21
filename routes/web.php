<?php

use App\Http\Controllers\Reports\GenerationRunController;
use App\Http\Controllers\Reports\ReferenceBatchController;
use App\Http\Controllers\Reports\ReferenceBatchStatusController;
use App\Http\Controllers\Reports\ReportController;
use App\Http\Controllers\Reports\ReportOutputController;
use App\Models\ReportOutput;
use Illuminate\Support\Facades\Route;
use Inertia\Inertia;
use Laravel\Fortify\Features;

Route::get('/', function () {
    return Inertia::render('welcome', [
        'canRegister' => Features::enabled(Features::registration()),
    ]);
})->name('home');

Route::middleware(['auth', 'verified'])->group(function () {
    Route::get('dashboard', function () {
        return Inertia::render('dashboard');
    })->name('dashboard');

    Route::resource('reports', ReportController::class)->only(['index', 'create', 'store', 'show']);
    Route::post('reports/{report}/reference-batches', [ReferenceBatchController::class, 'store'])
        ->name('reports.reference-batches.store');
    Route::post('reports/{report}/reference-batches/{referenceBatch}/queue', [ReferenceBatchController::class, 'queue'])
        ->name('reports.reference-batches.queue');
    Route::post('reports/{report}/generation-runs', [GenerationRunController::class, 'store'])
        ->name('reports.generation-runs.store');
    Route::post('reports/{report}/outputs/{type}', [ReportOutputController::class, 'store'])
        ->whereIn('type', ReportOutput::supportedTypes())
        ->name('reports.outputs.store');
});

Route::post('rag/webhooks/reference-batches', ReferenceBatchStatusController::class)
    ->name('rag.webhooks.reference-batches');

require __DIR__.'/settings.php';
