<?php

use App\Jobs\RetrieveReportOutput;
use App\Models\Report;
use App\Models\User;
use Illuminate\Support\Facades\Bus;

use function Pest\Laravel\actingAs;
use function Pest\Laravel\post;

it('prevents users from triggering outputs they do not own', function () {
    $user = User::factory()->create();
    $other = User::factory()->create();
    $report = Report::factory()->for($other)->create();

    actingAs($user)
        ->post(route('reports.outputs.store', [
            'report' => $report,
            'type' => 'penetapan',
        ]))
        ->assertForbidden();
});

it('queues a report output retrieval job', function () {
    Bus::fake();

    $user = User::factory()->create();
    $report = Report::factory()->for($user)->create();

    actingAs($user)
        ->post(route('reports.outputs.store', [
            'report' => $report,
            'type' => 'penetapan',
        ]))
        ->assertStatus(202)
        ->assertJsonStructure([
            'status',
            'job_key',
            'type',
        ]);

    expect($report->fresh()->penetapan_json['status'] ?? null)
        ->toEqual('queued');

    Bus::assertDispatched(RetrieveReportOutput::class, function (RetrieveReportOutput $job) use ($report) {
        return $job->report->is($report)
            && $job->type === 'penetapan';
    });
});
