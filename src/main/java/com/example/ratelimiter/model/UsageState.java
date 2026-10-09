package com.example.ratelimiter.model;

/** Which zone of the client's policy a request fell into. */
public enum UsageState {
    FREE,       // within the free quota - served, not charged
    BILLABLE,   // past the free quota - served and charged unitCostPaise
    BLOCKED     // past maxRequests - rejected with 429, not charged
}
