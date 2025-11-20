<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('reports', function (Blueprint $table) {
            $table->uuid('uuid')->nullable()->after('id');
        });

        DB::table('reports')
            ->whereNull('uuid')
            ->orderBy('id')
            ->chunkById(100, function ($reports) {
                foreach ($reports as $report) {
                    DB::table('reports')
                        ->where('id', $report->id)
                        ->update(['uuid' => (string) Str::uuid()]);
                }
            });

        Schema::table('reports', function (Blueprint $table) {
            $table->unique('uuid');
        });
    }

    public function down(): void
    {
        Schema::table('reports', function (Blueprint $table) {
            $table->dropUnique(['uuid']);
            $table->dropColumn('uuid');
        });
    }
};
