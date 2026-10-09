package com.example.ratelimiter.model;

/** A client's effective policy, and whether it is custom or the default. */
public record PolicyView(String clientId, Policy policy, boolean customPolicy) {
}
