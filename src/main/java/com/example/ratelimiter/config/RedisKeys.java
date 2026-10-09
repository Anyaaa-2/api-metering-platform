package com.example.ratelimiter.config;

/** Single place that defines every Redis key the service uses. */
public final class RedisKeys {

    public static final String CLIENTS = "clients";

    private RedisKeys() {
    }

    public static String policy(String clientId) {
        return "policy:" + clientId;
    }

    public static String usage(String clientId) {
        return "usage:" + clientId;
    }

    public static String bill(String clientId) {
        return "bill:" + clientId;
    }

    public static String history(String clientId, long epochMinute) {
        return "history:" + clientId + ":" + epochMinute;
    }
}
