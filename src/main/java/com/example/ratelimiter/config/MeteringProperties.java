package com.example.ratelimiter.config;

import com.example.ratelimiter.model.Policy;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Bound from the "metering.*" keys in application.properties.
 * The default policy applies to any client without a custom one in Redis.
 */
@ConfigurationProperties(prefix = "metering")
public record MeteringProperties(
        int defaultFreeLimit,
        int defaultMaxRequests,
        long defaultUnitCostPaise,
        int defaultWindowSeconds,
        int historyTtlSeconds,
        String adminApiKey
) {
    public Policy defaultPolicy() {
        return new Policy(defaultFreeLimit, defaultMaxRequests, defaultUnitCostPaise, defaultWindowSeconds);
    }
}
