<?php

namespace Database\Factories;

use App\Models\GenerationRun;
use App\Models\Report;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;

class GenerationRunFactory extends Factory
{
    protected $model = GenerationRun::class;

    public function definition(): array
    {
        $start = now()->subMinutes($this->faker->numberBetween(1, 120));
        $end = (clone $start)->addMinutes($this->faker->numberBetween(1, 20));

        return [
            'report_id' => Report::factory(),
            'triggered_by' => User::factory(),
            'status' => $this->faker->randomElement(['pending', 'running', 'completed', 'failed']),
            'automation_job_id' => $this->faker->uuid(),
            'started_at' => $start,
            'finished_at' => $end,
            'summary' => [
                'sections_generated' => $this->faker->numberBetween(1, 15),
            ],
            'error_message' => null,
            'payload' => [
                'references_used' => $this->faker->numberBetween(50, 150),
            ],
        ];
    }
}
