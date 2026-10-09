package com.example.ratelimiter.model;

/** The outcome of metering one request, as returned by the Lua script. */
public record MeterDecision(
        UsageState state,
        long used,
        long remaining,
        long freeRemaining,
        long billPaise,
        long resetInSeconds,
        long maxRequests
) {
}
