<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Str;

class Report extends Model
{
    use HasFactory;

    protected $guarded = [];

    protected $casts = [
        'metadata' => 'array',
        'last_generated_at' => 'datetime',
        'uuid' => 'string',
    ];

    protected static function booted(): void
    {
        static::creating(function (Report $report) {
            if (empty($report->uuid)) {
                $report->uuid = (string) Str::uuid();
            }
        });
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function sections(): HasMany
    {
        return $this->hasMany(ReportSection::class)->orderBy('sequence');
    }

    public function referenceBatches(): HasMany
    {
        return $this->hasMany(ReferenceBatch::class);
    }

    public function references(): HasMany
    {
        return $this->hasMany(ReportReference::class);
    }

    public function generationRuns(): HasMany
    {
        return $this->hasMany(GenerationRun::class);
    }

    public function outputs(): HasMany
    {
        return $this->hasMany(ReportOutput::class);
    }
}
