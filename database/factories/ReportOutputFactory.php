<?php

namespace Database\Factories;

use App\Models\Report;
use App\Models\ReportOutput;
use Illuminate\Database\Eloquent\Factories\Factory;

class ReportOutputFactory extends Factory
{
    protected $model = ReportOutput::class;

    public function definition(): array
    {
        $startedAt = now()->subMinutes($this->faker->numberBetween(1, 90));
        $status = $this->faker->randomElement([
            ReportOutput::STATUS_PENDING,
            ReportOutput::STATUS_QUEUED,
            ReportOutput::STATUS_PROCESSING,
            ReportOutput::STATUS_COMPLETED,
            ReportOutput::STATUS_FAILED,
        ]);
        $finishedAt = in_array($status, [ReportOutput::STATUS_COMPLETED, ReportOutput::STATUS_FAILED], true)
            ? (clone $startedAt)->addMinutes($this->faker->numberBetween(1, 15))
            : null;

        return [
            'report_id' => Report::factory(),
            'type' => $this->faker->randomElement(ReportOutput::supportedTypes()),
            'status' => $status,
            'job_id' => $this->faker->uuid(),
            'artifact_path' => 'outputs/'.$this->faker->uuid().'.json',
            'payload' => [
                'summary' => $this->faker->sentence(),
            ],
            'metadata' => [
                'records' => $this->faker->numberBetween(5, 50),
            ],
            'started_at' => $startedAt,
            'finished_at' => $finishedAt,
            'error_message' => null,
        ];
    }
}
