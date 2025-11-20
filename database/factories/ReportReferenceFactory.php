<?php

namespace Database\Factories;

use App\Models\ReferenceBatch;
use App\Models\Report;
use App\Models\ReportReference;
use Illuminate\Database\Eloquent\Factories\Factory;

class ReportReferenceFactory extends Factory
{
    protected $model = ReportReference::class;

    public function definition(): array
    {
        return [
            'report_id' => Report::factory(),
            'batch_id' => ReferenceBatch::factory(),
            'citation_key' => $this->faker->unique()->bothify('REF-####'),
            'title' => $this->faker->sentence(6),
            'authors' => $this->faker->name(),
            'publication_year' => $this->faker->year(),
            'source_type' => $this->faker->randomElement(['journal', 'book', 'website']),
            'abstract' => $this->faker->paragraph(),
            'raw_payload' => json_encode(['url' => $this->faker->url()]),
            'content_hash' => $this->faker->sha1(),
            'metadata' => [
                'language' => $this->faker->randomElement(['id', 'en']),
            ],
        ];
    }
}
