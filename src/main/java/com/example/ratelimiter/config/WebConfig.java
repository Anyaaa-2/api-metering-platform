package com.example.ratelimiter.config;

import com.example.ratelimiter.interceptor.AdminAuthInterceptor;
import com.example.ratelimiter.interceptor.MeteringInterceptor;
import com.example.ratelimiter.service.MeteringService;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final MeteringService meteringService;
    private final MeteringProperties properties;

    public WebConfig(MeteringService meteringService, MeteringProperties properties) {
        this.meteringService = meteringService;
        this.properties = properties;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Customer traffic: metered and billed.
        registry.addInterceptor(new MeteringInterceptor(meteringService))
                .addPathPatterns("/api/**");
        // Operator traffic: protected by an API key, never metered.
        registry.addInterceptor(new AdminAuthInterceptor(properties.adminApiKey()))
                .addPathPatterns("/admin/**");
    }
}
