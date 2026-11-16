package br.pucrs.tcc2.reactive.domain.cpu;

import br.pucrs.tcc2.reactive.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.reactive.domain.cpu.port.api.CpuApiPort;
import br.pucrs.tcc2.reactive.domain.common.Pbkdf2Workload;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class CpuService implements CpuApiPort {
    private final int iterations;
    private final ExecutionMode executionMode;

    public CpuService(@Value("${tcc.cpu.iterations:200000}") int iterations,
            @Value("${tcc.cpu.execution-mode:event-loop}") String executionMode) {
        if (iterations <= 0) throw new IllegalArgumentException("tcc.cpu.iterations must be positive");
        this.iterations = iterations;
        this.executionMode = ExecutionMode.parse(executionMode);
    }

    @Override
    public Mono<CpuDto> execute() {
        Mono<CpuDto> workload = Mono.fromSupplier(this::compute);
        return executionMode == ExecutionMode.BOUNDED_ELASTIC
                ? workload.subscribeOn(Schedulers.boundedElastic())
                : workload;
    }

    private CpuDto compute() {
        return Pbkdf2Workload.execute(iterations);
    }

    private enum ExecutionMode {
        EVENT_LOOP, BOUNDED_ELASTIC;

        private static ExecutionMode parse(String value) {
            return switch (value) {
                case "event-loop" -> EVENT_LOOP;
                case "bounded-elastic" -> BOUNDED_ELASTIC;
                default -> throw new IllegalArgumentException(
                        "tcc.cpu.execution-mode must be event-loop or bounded-elastic");
            };
        }
    }
}
