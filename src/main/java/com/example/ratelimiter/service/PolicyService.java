package com.example.ratelimiter.service;

import com.example.ratelimiter.config.MeteringProperties;
import com.example.ratelimiter.config.RedisKeys;
import com.example.ratelimiter.model.Policy;
import com.example.ratelimiter.model.PolicyView;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Service
public class PolicyService {

    private final StringRedisTemplate redis;
    private final MeteringProperties properties;

    public PolicyService(StringRedisTemplate redis, MeteringProperties properties) {
        this.redis = redis;
        this.properties = properties;
    }

    public PolicyView get(String clientId) {
        Map<Object, Object> stored = redis.opsForHash().entries(RedisKeys.policy(clientId));
        if (stored.isEmpty()) {
            return new PolicyView(clientId, properties.defaultPolicy(), false);
        }
        Policy d = properties.defaultPolicy();
        Policy policy = new Policy(
                intField(stored, "freeLimit", d.freeLimit()),
                intField(stored, "maxRequests", d.maxRequests()),
                longField(stored, "unitCostPaise", d.unitCostPaise()),
                intField(stored, "windowSeconds", d.windowSeconds())
        );
        return new PolicyView(clientId, policy, true);
    }

    /**
     * Stores a custom policy. The Lua script reads it on the client's very
     * next request; a changed windowSeconds applies from the next window.
     */
    public PolicyView put(String clientId, Policy policy) {
        List<String> errors = policy.validate();
        if (!errors.isEmpty()) {
            throw new InvalidPolicyException(errors);
        }
        redis.opsForHash().putAll(RedisKeys.policy(clientId), Map.of(
                "freeLimit", String.valueOf(policy.freeLimit()),
                "maxRequests", String.valueOf(policy.maxRequests()),
                "unitCostPaise", String.valueOf(policy.unitCostPaise()),
                "windowSeconds", String.valueOf(policy.windowSeconds())
        ));
        redis.opsForSet().add(RedisKeys.CLIENTS, clientId);
        return new PolicyView(clientId, policy, true);
    }

    /** Removes a custom policy so the client falls back to the default. */
    public PolicyView reset(String clientId) {
        redis.delete(RedisKeys.policy(clientId));
        return get(clientId);
    }

    private static int intField(Map<Object, Object> map, String field, int fallback) {
        Object v = map.get(field);
        return v == null ? fallback : Integer.parseInt(v.toString());
    }

    private static long longField(Map<Object, Object> map, String field, long fallback) {
        Object v = map.get(field);
        return v == null ? fallback : Long.parseLong(v.toString());
    }

    public static class InvalidPolicyException extends RuntimeException {
        private final List<String> errors;

        public InvalidPolicyException(List<String> errors) {
            super(String.join("; ", errors));
            this.errors = errors;
        }

        public List<String> getErrors() {
            return errors;
        }
    }
}
