package com.example.ratelimiter.service;

import com.example.ratelimiter.config.RedisKeys;
import com.example.ratelimiter.model.PolicyView;
import com.example.ratelimiter.model.UsageReport;
import com.example.ratelimiter.model.UsageReport.MinuteBucket;
import com.example.ratelimiter.model.UsageReport.Totals;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/** Read-only views over metering data, used by the admin API and the AI advisor. */
@Service
public class UsageService {

    public static final int MAX_MINUTES = 1440;

    private final StringRedisTemplate redis;
    private final PolicyService policyService;

    public UsageService(StringRedisTemplate redis, PolicyService policyService) {
        this.redis = redis;
        this.policyService = policyService;
    }

    public Set<String> clients() {
        Set<String> members = redis.opsForSet().members(RedisKeys.CLIENTS);
        return members == null ? Set.of() : new TreeSet<>(members);
    }

    public UsageReport report(String clientId, int minutes) {
        int span = Math.max(1, Math.min(minutes, MAX_MINUTES));
        long nowMinute = Instant.now().getEpochSecond() / 60;
        long firstMinute = nowMinute - span + 1;

        // Fetch every minute bucket in ONE pipelined round trip
        // instead of one network call per minute.
        List<Object> buckets = redis.executePipelined((RedisCallback<Object>) connection -> {
            for (long m = firstMinute; m <= nowMinute; m++) {
                connection.hashCommands().hGetAll(bytes(RedisKeys.history(clientId, m)));
            }
            return null;
        });

        List<MinuteBucket> history = new ArrayList<>();
        long total = 0, free = 0, billable = 0, blocked = 0, cost = 0;
        for (int i = 0; i < buckets.size(); i++) {
            if (!(buckets.get(i) instanceof Map<?, ?> fields) || fields.isEmpty()) {
                continue; // no traffic that minute
            }
            MinuteBucket b = new MinuteBucket(
                    Instant.ofEpochSecond((firstMinute + i) * 60).toString(),
                    field(fields, "total"),
                    field(fields, "FREE"),
                    field(fields, "BILLABLE"),
                    field(fields, "BLOCKED"),
                    field(fields, "costPaise")
            );
            history.add(b);
            total += b.total();
            free += b.free();
            billable += b.billable();
            blocked += b.blocked();
            cost += b.costPaise();
        }

        PolicyView policy = policyService.get(clientId);
        Long ttl = redis.getExpire(RedisKeys.usage(clientId));

        return new UsageReport(
                clientId,
                policy,
                parseOrZero(redis.opsForValue().get(RedisKeys.usage(clientId))),
                ttl == null || ttl < 0 ? 0 : ttl,
                parseOrZero(redis.opsForValue().get(RedisKeys.bill(clientId))),
                span,
                new Totals(total, free, billable, blocked, cost),
                history
        );
    }

    private static byte[] bytes(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    private static long field(Map<?, ?> fields, String name) {
        Object v = fields.get(name);
        return v == null ? 0 : Long.parseLong(v.toString());
    }

    private static long parseOrZero(String s) {
        return s == null ? 0 : Long.parseLong(s);
    }
}
