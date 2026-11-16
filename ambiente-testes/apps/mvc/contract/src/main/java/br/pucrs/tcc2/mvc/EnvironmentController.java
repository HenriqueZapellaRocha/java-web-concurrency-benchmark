package br.pucrs.tcc2.mvc;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootVersion;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EnvironmentController {
    private final String model;

    public EnvironmentController(@Value("${tcc.model}") String model) {
        this.model = model;
    }

    @GetMapping("/environment")
    public EnvironmentSnapshot environment() {
        return EnvironmentSnapshot.capture(model, "spring-mvc/tomcat", SpringBootVersion.getVersion());
    }
}

