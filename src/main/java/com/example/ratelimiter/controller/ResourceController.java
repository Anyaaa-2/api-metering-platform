package com.example.ratelimiter.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

@RestController
public class ResourceController {

    // This stands in for whatever real business logic a company would put
    // here. The point of the project is everything that happens BEFORE
    // this method is allowed to run.
    @GetMapping("/api/resource")
    public Map<String, Object> getResource() {
        return Map.of(
                "message", "Request served successfully",
                "timestamp", Instant.now().toString()
        );
    }
}
