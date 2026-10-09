package com.example.ratelimiter.interceptor;

import com.example.ratelimiter.model.MeterDecision;
import com.example.ratelimiter.model.UsageState;
import com.example.ratelimiter.service.MeteringService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.util.regex.Pattern;

/** Meters every /api/** request before the controller is allowed to run. */
public class MeteringInterceptor implements HandlerInterceptor {

    // Client ids become Redis keys, so keep them short and predictable.
    // ':' is allowed because IPv6 fallback addresses contain it.
    private static final Pattern CLIENT_ID = Pattern.compile("[A-Za-z0-9._:-]{1,64}");

    private final MeteringService meteringService;

    public MeteringInterceptor(MeteringService meteringService) {
        this.meteringService = meteringService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws IOException {
        String clientId = request.getHeader("X-Client-Id");
        if (clientId == null || clientId.isBlank()) {
            clientId = request.getRemoteAddr();
        }
        if (!CLIENT_ID.matcher(clientId).matches()) {
            writeJson(response, 400, "{\"error\":\"invalid X-Client-Id\"}");
            return false;
        }

        MeterDecision d = meteringService.meter(clientId);

        response.setHeader("X-Usage-State", d.state().name());
        response.setHeader("X-RateLimit-Limit", String.valueOf(d.maxRequests()));
        response.setHeader("X-RateLimit-Remaining", String.valueOf(d.remaining()));
        response.setHeader("X-Free-Remaining", String.valueOf(d.freeRemaining()));
        response.setHeader("X-Bill-Paise", String.valueOf(d.billPaise()));

        if (d.state() == UsageState.BLOCKED) {
            response.setHeader("Retry-After", String.valueOf(d.resetInSeconds()));
            writeJson(response, 429,
                    "{\"error\":\"request limit reached\",\"retryAfterSeconds\":" + d.resetInSeconds() + "}");
            return false;
        }
        return true;
    }

    private static void writeJson(HttpServletResponse response, int status, String body) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(body);
    }
}
