<?php

use App\Models\Report;

it('assigns a uuid when reports are created', function () {
    $report = Report::factory()->create(['uuid' => null]);

    expect($report->uuid)
        ->not->toBeNull()
        ->and(strlen($report->uuid))
        ->toBe(36);

    $anotherReport = Report::factory()->create();

    expect($anotherReport->uuid)->not->toBe($report->uuid);
});
