package br.pucrs.tcc2.reactive;

import org.springframework.boot.SpringBootVersion;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class EnvironmentController {
    @GetMapping("/environment")
    public Mono<EnvironmentSnapshot> environment() {
        return Mono.fromSupplier(() -> EnvironmentSnapshot.capture(
                "m3", "spring-webflux/netty", SpringBootVersion.getVersion(), Schedulers.isInNonBlockingThread()));
    }
}
