<?php

use App\Models\Report;
use App\Models\User;

use function Pest\Laravel\actingAs;
use function Pest\Laravel\get;
use function Pest\Laravel\post;

it('redirects guests away from the reports index', function () {
    get(route('reports.index'))->assertRedirect(route('login'));
});

it('allows authenticated users to load their reports', function () {
    $user = User::factory()->create();
    Report::factory()->for($user)->create(['name' => 'LED Teknik 2025']);

    actingAs($user)->get(route('reports.index'))
        ->assertOk()
        ->assertSee('LED Teknik 2025');
});

it('stores a new report with default metadata', function () {
    $user = User::factory()->create();

    actingAs($user)->post(route('reports.store'), [
        'name' => 'LED Farmasi',
        'program_name' => 'Farmasi S1',
    ])->assertRedirect();

    $this->assertDatabaseHas('reports', [
        'name' => 'LED Farmasi',
        'program_name' => 'Farmasi S1',
        'user_id' => $user->id,
    ]);
});

it('prevents users from viewing reports they do not own', function () {
    $user = User::factory()->create();
    $other = User::factory()->create();
    $report = Report::factory()->for($other)->create();

    actingAs($user)->get(route('reports.show', $report))
        ->assertForbidden();
});
