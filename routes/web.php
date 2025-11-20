<?php

use App\Http\Controllers\Reports\GenerationRunController;
use App\Http\Controllers\Reports\ReferenceBatchController;
use App\Http\Controllers\Reports\ReportController;
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
    Route::post('reports/{report}/generation-runs', [GenerationRunController::class, 'store'])
        ->name('reports.generation-runs.store');
});

require __DIR__.'/settings.php';
