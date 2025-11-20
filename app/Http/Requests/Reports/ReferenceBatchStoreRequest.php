<?php

namespace App\Http\Requests\Reports;

use Illuminate\Foundation\Http\FormRequest;

class ReferenceBatchStoreRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user() !== null;
    }

    public function rules(): array
    {
        return [
            'file' => ['nullable', 'file', 'max:20480'],
            'source_filename' => ['nullable', 'string', 'max:255'],
            'notes' => ['nullable', 'string'],
            'total_references' => ['nullable', 'integer', 'min:0'],
            'metadata' => ['nullable', 'array'],
        ];
    }
}
