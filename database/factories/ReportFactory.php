<?php

namespace Database\Factories;

use App\Models\Report;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Str;

class ReportFactory extends Factory
{
    protected $model = Report::class;

    public function definition(): array
    {
        $name = $this->faker->sentence(3);

        return [
            'user_id' => User::factory(),
            'name' => $name,
            'slug' => Str::slug($name.'-'.Str::random(5)),
            'status' => $this->faker->randomElement(['draft', 'running', 'completed', 'failed']),
            'program_name' => $this->faker->company().' '.$this->faker->randomElement(['S1', 'S2', 'S3']),
            'output_path' => null,
            'automation_job_id' => null,
            'last_generated_at' => null,
            'last_error' => null,
            'metadata' => [
                'accreditation_level' => $this->faker->randomElement(['A', 'B', 'Unggul']),
            ],
        ];
    }
}
