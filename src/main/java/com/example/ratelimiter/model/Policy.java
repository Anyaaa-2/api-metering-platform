package com.example.ratelimiter.model;

import java.util.ArrayList;
import java.util.List;

/**
 * A client's plan for each window:
 *   requests 1..freeLimit             -> FREE
 *   requests freeLimit+1..maxRequests -> BILLABLE at unitCostPaise each
 *   requests beyond maxRequests       -> BLOCKED
 *
 * Money is stored in integer paise (1 rupee = 100 paise) so billing
 * never accumulates floating-point rounding errors.
 */
public record Policy(int freeLimit, int maxRequests, long unitCostPaise, int windowSeconds) {

    public static final int MAX_WINDOW_SECONDS = 86_400;

    /** Returns a list of problems; empty means the policy is valid. */
    public List<String> validate() {
        List<String> errors = new ArrayList<>();
        if (freeLimit < 0) {
            errors.add("freeLimit must be >= 0");
        }
        if (maxRequests < 1) {
            errors.add("maxRequests must be >= 1");
        }
        if (freeLimit > maxRequests) {
            errors.add("freeLimit must not exceed maxRequests");
        }
        if (unitCostPaise < 0) {
            errors.add("unitCostPaise must be >= 0");
        }
        if (windowSeconds < 1 || windowSeconds > MAX_WINDOW_SECONDS) {
            errors.add("windowSeconds must be between 1 and " + MAX_WINDOW_SECONDS);
        }
        return errors;
    }
}
