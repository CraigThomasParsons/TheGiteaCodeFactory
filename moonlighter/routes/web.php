<?php

declare(strict_types=1);

use App\Livewire\JobBoard;
use App\Livewire\ScheduleCalendar;
use Illuminate\Support\Facades\Route;

// The live job board is the application's home page.
Route::get('/', JobBoard::class);

// Active-hours calendar for weekly windows and overrides.
Route::get('/schedule', ScheduleCalendar::class);
