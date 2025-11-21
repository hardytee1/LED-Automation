<?php

namespace App\Providers;

use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        if (class_exists(\Faker\Generator::class)) {
            $this->app->singleton(\Faker\Generator::class, function ($app) {
                $locale = $app['config']->get('app.faker_locale', 'en_US');

                return \Faker\Factory::create($locale);
            });
        }
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        $postMax = config('app.post_max_size');
        $uploadMax = config('app.upload_max_filesize') ?: $postMax;

        if (! empty($postMax)) {
            @ini_set('post_max_size', (string) $postMax);
        }

        if (! empty($uploadMax)) {
            @ini_set('upload_max_filesize', (string) $uploadMax);
        }
    }
}
