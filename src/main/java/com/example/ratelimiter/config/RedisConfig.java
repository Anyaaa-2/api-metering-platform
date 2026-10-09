package com.example.ratelimiter.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import java.util.List;

@Configuration
public class RedisConfig {

    @Bean
    public StringRedisTemplate stringRedisTemplate(RedisConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }

    /**
     * The metering script counts, classifies (FREE / BILLABLE / BLOCKED),
     * bills and records history for a request as ONE atomic Redis operation,
     * so the quota and the bill stay exact across any number of pods.
     */
    @Bean
    @SuppressWarnings("rawtypes")
    public DefaultRedisScript<List> meteringScript() {
        DefaultRedisScript<List> script = new DefaultRedisScript<>();
        script.setLocation(new ClassPathResource("metering.lua"));
        script.setResultType(List.class);
        return script;
    }
}
