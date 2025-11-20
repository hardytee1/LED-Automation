<?php

namespace Database\Factories;

use App\Models\ReferenceBatch;
use App\Models\Report;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;

class ReferenceBatchFactory extends Factory
{
    protected $model = ReferenceBatch::class;

    public function definition(): array
    {
        return [
            'report_id' => Report::factory(),
            'uploaded_by' => User::factory(),
            'source_filename' => $this->faker->lexify('references-????.xlsx'),
            'storage_path' => 'references/'.$this->faker->uuid.'.xlsx',
            'total_references' => $this->faker->numberBetween(50, 200),
            'processed_references' => $this->faker->numberBetween(0, 200),
            'status' => $this->faker->randomElement(['pending', 'processing', 'completed', 'failed']),
            'notes' => $this->faker->optional()->sentence(),
            'metadata' => [
                'parser' => 'notebook',
            ],
            'submitted_at' => now()->subMinutes($this->faker->numberBetween(10, 600)),
        ];
    }
}
