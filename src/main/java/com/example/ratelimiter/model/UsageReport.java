package com.example.ratelimiter.model;

import java.util.List;

/**
 * Everything the AI usage advisor needs to reason about one client:
 * its plan, where it stands right now, and minute-by-minute history.
 */
public record UsageReport(
        String clientId,
        PolicyView policy,
        long currentWindowUsed,
        long windowResetsInSeconds,
        long billPaise,
        int minutesCovered,
        Totals totals,
        List<MinuteBucket> history
) {

    public record Totals(long total, long free, long billable, long blocked, long costPaise) {
    }

    /** One minute of traffic. Minutes with no traffic are omitted. */
    public record MinuteBucket(String minute, long total, long free, long billable, long blocked, long costPaise) {
    }
}
