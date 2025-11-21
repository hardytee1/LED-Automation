<?php

namespace Database\Seeders;

use App\Models\GenerationRun;
use App\Models\ReferenceBatch;
use App\Models\Report;
use App\Models\ReportReference;
use App\Models\ReportSection;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class DatabaseSeeder extends Seeder
{
    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        $user = User::firstOrCreate(
            ['email' => 'test@example.com'],
            [
                'name' => 'Test User',
                'password' => Hash::make('password'),
                'email_verified_at' => now(),
            ]
        );

        $reports = Report::factory()
            ->count(3)
            ->for($user)
            ->has(ReportSection::factory()->count(6), 'sections')
            ->create();

        foreach ($reports as $report) {
            $batches = ReferenceBatch::factory()
                ->count(2)
                ->for($report)
                ->for($user, 'uploadedBy')
                ->create();

            foreach ($batches as $batch) {
                ReportReference::factory()
                    ->count(20)
                    ->for($report)
                    ->for($batch, 'batch')
                    ->create();
            }

            GenerationRun::factory()
                ->count(2)
                ->for($report)
                ->for($user, 'triggeredBy')
                ->create();

        }
    }
}
