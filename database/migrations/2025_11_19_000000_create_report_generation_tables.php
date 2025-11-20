<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('reports', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('name');
            $table->string('slug')->unique();
            $table->string('status')->default('draft');
            $table->string('program_name')->nullable();
            $table->string('output_path')->nullable();
            $table->string('automation_job_id')->nullable();
            $table->timestamp('last_generated_at')->nullable();
            $table->text('last_error')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();
        });

        Schema::create('report_sections', function (Blueprint $table) {
            $table->id();
            $table->foreignId('report_id')->constrained('reports')->cascadeOnDelete();
            $table->string('title');
            $table->unsignedInteger('sequence')->default(1);
            $table->string('status')->default('pending');
            $table->longText('content')->nullable();
            $table->unsignedInteger('tokens_used')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();
        });

        Schema::create('reference_batches', function (Blueprint $table) {
            $table->id();
            $table->foreignId('report_id')->constrained('reports')->cascadeOnDelete();
            $table->foreignId('uploaded_by')->constrained('users')->cascadeOnDelete();
            $table->string('source_filename')->nullable();
            $table->string('storage_path')->nullable();
            $table->unsignedInteger('total_references')->default(0);
            $table->unsignedInteger('processed_references')->default(0);
            $table->string('status')->default('pending');
            $table->text('notes')->nullable();
            $table->json('metadata')->nullable();
            $table->timestamp('submitted_at')->nullable();
            $table->timestamps();
        });

        Schema::create('report_references', function (Blueprint $table) {
            $table->id();
            $table->foreignId('report_id')->constrained('reports')->cascadeOnDelete();
            $table->foreignId('batch_id')->nullable()->constrained('reference_batches')->nullOnDelete();
            $table->string('citation_key')->nullable();
            $table->string('title');
            $table->string('authors')->nullable();
            $table->unsignedSmallInteger('publication_year')->nullable();
            $table->string('source_type')->nullable();
            $table->text('abstract')->nullable();
            $table->text('raw_payload')->nullable();
            $table->string('content_hash', 64)->nullable();
            $table->json('metadata')->nullable();
            $table->timestamps();

            $table->unique(['report_id', 'citation_key']);
        });

        Schema::create('generation_runs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('report_id')->constrained('reports')->cascadeOnDelete();
            $table->foreignId('triggered_by')->constrained('users')->cascadeOnDelete();
            $table->string('status')->default('pending');
            $table->string('automation_job_id')->nullable();
            $table->timestamp('started_at')->nullable();
            $table->timestamp('finished_at')->nullable();
            $table->json('summary')->nullable();
            $table->text('error_message')->nullable();
            $table->json('payload')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('generation_runs');
        Schema::dropIfExists('report_references');
        Schema::dropIfExists('reference_batches');
        Schema::dropIfExists('report_sections');
        Schema::dropIfExists('reports');
    }
};
