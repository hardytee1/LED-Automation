<?php

use App\Jobs\RetrieveReportOutput;
use App\Models\Report;
use App\Models\ReportOutput;
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
            'type' => ReportOutput::TYPE_PENETAPAN,
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
            'type' => ReportOutput::TYPE_PENETAPAN,
        ]))
        ->assertStatus(202)
        ->assertJsonStructure([
            'output' => ['id', 'type', 'status', 'job_id', 'created_at'],
        ]);

    $this->assertDatabaseHas('report_outputs', [
        'report_id' => $report->id,
        'type' => ReportOutput::TYPE_PENETAPAN,
        'status' => ReportOutput::STATUS_QUEUED,
    ]);

    Bus::assertDispatched(RetrieveReportOutput::class, function (RetrieveReportOutput $job) use ($report) {
        return $job->output->report_id === $report->id
            && $job->output->type === ReportOutput::TYPE_PENETAPAN;
    });
});
