package com.example.ratelimiter.controller;

import com.example.ratelimiter.model.Policy;
import com.example.ratelimiter.model.PolicyView;
import com.example.ratelimiter.model.UsageReport;
import com.example.ratelimiter.service.PolicyService;
import com.example.ratelimiter.service.PolicyService.InvalidPolicyException;
import com.example.ratelimiter.service.UsageService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.Set;

/**
 * Operator API: manage policies and read usage. The AI usage advisor
 * uses only the GET endpoints - it recommends, it never writes.
 */
@RestController
@RequestMapping("/admin")
public class AdminController {

    private final PolicyService policyService;
    private final UsageService usageService;

    public AdminController(PolicyService policyService, UsageService usageService) {
        this.policyService = policyService;
        this.usageService = usageService;
    }

    @GetMapping("/clients")
    public Set<String> clients() {
        return usageService.clients();
    }

    @GetMapping("/policy/{clientId}")
    public PolicyView getPolicy(@PathVariable String clientId) {
        return policyService.get(clientId);
    }

    @PutMapping("/policy/{clientId}")
    public PolicyView putPolicy(@PathVariable String clientId, @RequestBody Policy policy) {
        return policyService.put(clientId, policy);
    }

    @DeleteMapping("/policy/{clientId}")
    public PolicyView resetPolicy(@PathVariable String clientId) {
        return policyService.reset(clientId);
    }

    @GetMapping("/usage/{clientId}")
    public UsageReport usage(@PathVariable String clientId,
                             @RequestParam(defaultValue = "60") int minutes) {
        return usageService.report(clientId, minutes);
    }

    @ExceptionHandler(InvalidPolicyException.class)
    public ResponseEntity<Map<String, Object>> invalidPolicy(InvalidPolicyException e) {
        return ResponseEntity.badRequest().body(Map.of("error", "invalid policy", "details", e.getErrors()));
    }
}
