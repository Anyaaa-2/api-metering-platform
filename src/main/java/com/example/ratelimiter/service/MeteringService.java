package com.example.ratelimiter.service;

import com.example.ratelimiter.config.MeteringProperties;
import com.example.ratelimiter.config.RedisKeys;
import com.example.ratelimiter.model.MeterDecision;
import com.example.ratelimiter.model.Policy;
import com.example.ratelimiter.model.UsageState;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;

/**
 * The hot path: called once per customer request. Exactly one Redis
 * round trip, and no LLM or other slow dependency anywhere near it.
 */
@Service
public class MeteringService {

    private final StringRedisTemplate redis;
    @SuppressWarnings("rawtypes")
    private final DefaultRedisScript<List> meteringScript;
    private final MeteringProperties properties;

    @SuppressWarnings("rawtypes")
    public MeteringService(StringRedisTemplate redis,
                           DefaultRedisScript<List> meteringScript,
                           MeteringProperties properties) {
        this.redis = redis;
        this.meteringScript = meteringScript;
        this.properties = properties;
    }

    public MeterDecision meter(String clientId) {
        long epochMinute = Instant.now().getEpochSecond() / 60;
        Policy defaults = properties.defaultPolicy();

        List<String> keys = List.of(
                RedisKeys.policy(clientId),
                RedisKeys.usage(clientId),
                RedisKeys.bill(clientId),
                RedisKeys.history(clientId, epochMinute),
                RedisKeys.CLIENTS
        );

        List<?> result = redis.execute(
                meteringScript,
                keys,
                clientId,
                String.valueOf(defaults.freeLimit()),
                String.valueOf(defaults.maxRequests()),
                String.valueOf(defaults.unitCostPaise()),
                String.valueOf(defaults.windowSeconds()),
                String.valueOf(properties.historyTtlSeconds())
        );

        if (result == null || result.size() < 7) {
            throw new IllegalStateException("Unexpected metering script result: " + result);
        }

        return new MeterDecision(
                UsageState.valueOf(String.valueOf(result.get(0))),
                asLong(result.get(1)),
                asLong(result.get(2)),
                asLong(result.get(3)),
                asLong(result.get(4)),
                asLong(result.get(5)),
                asLong(result.get(6))
        );
    }

    // Redis integers arrive as Long, but parse via String to be safe.
    private static long asLong(Object value) {
        return Long.parseLong(String.valueOf(value));
    }
}
