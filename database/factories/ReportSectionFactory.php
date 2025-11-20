<?php

namespace Database\Factories;

use App\Models\Report;
use App\Models\ReportSection;
use Illuminate\Database\Eloquent\Factories\Factory;

class ReportSectionFactory extends Factory
{
    protected $model = ReportSection::class;

    public function definition(): array
    {
        return [
            'report_id' => Report::factory(),
            'title' => $this->faker->sentence(4),
            'sequence' => $this->faker->numberBetween(1, 20),
            'status' => $this->faker->randomElement(['pending', 'generating', 'completed', 'failed']),
            'content' => $this->faker->paragraphs(3, true),
            'tokens_used' => $this->faker->numberBetween(200, 4000),
            'metadata' => [
                'rubric' => $this->faker->sentence(),
            ],
        ];
    }
}
