<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Report extends Model
{
    use HasFactory;

    protected $guarded = [];

    protected $casts = [
        'metadata' => 'array',
        'last_generated_at' => 'datetime',
    ];

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
}
