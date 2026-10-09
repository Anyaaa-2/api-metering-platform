package com.example.ratelimiter.interceptor;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Guards /admin/** with a shared API key (X-Admin-Key header).
 * Fails closed: if no key is configured, the admin API is disabled,
 * because the service sits behind a public LoadBalancer.
 */
public class AdminAuthInterceptor implements HandlerInterceptor {

    private final byte[] expectedKey;

    public AdminAuthInterceptor(String adminApiKey) {
        this.expectedKey = adminApiKey == null || adminApiKey.isBlank()
                ? null
                : adminApiKey.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws IOException {
        if (expectedKey == null) {
            reject(response, 503, "admin API disabled: ADMIN_API_KEY is not configured");
            return false;
        }
        String provided = request.getHeader("X-Admin-Key");
        // Constant-time comparison, so response timing can't leak the key.
        if (provided == null || !MessageDigest.isEqual(expectedKey, provided.getBytes(StandardCharsets.UTF_8))) {
            reject(response, 401, "missing or invalid X-Admin-Key");
            return false;
        }
        return true;
    }

    private static void reject(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write("{\"error\":\"" + message + "\"}");
    }
}
