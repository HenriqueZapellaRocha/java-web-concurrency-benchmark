package br.pucrs.tcc2.reactive.domain.mixed;

import br.pucrs.tcc2.reactive.domain.common.Sha256Workload;
import br.pucrs.tcc2.reactive.domain.io.model.input.IoInput;
import br.pucrs.tcc2.reactive.domain.io.port.api.IoApiPort;
import br.pucrs.tcc2.reactive.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.reactive.domain.mixed.model.input.MixedInput;
import br.pucrs.tcc2.reactive.domain.mixed.port.api.MixedApiPort;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class MixedService implements MixedApiPort {
    private final IoApiPort ioApiPort;
    private final int iterations;
    private final ExecutionMode executionMode;

    public MixedService(IoApiPort ioApiPort,
            @Value("${tcc.mixed.cpu-iterations:10000}") int iterations,
            @Value("${tcc.mixed.cpu-execution-mode:event-loop}") String executionMode) {
        if (iterations <= 0) throw new IllegalArgumentException("tcc.mixed.cpu-iterations must be positive");
        this.ioApiPort = ioApiPort;
        this.iterations = iterations;
        this.executionMode = ExecutionMode.parse(executionMode);
    }

    @Override
    public Mono<MixedDto> execute(MixedInput input) {
        Mono<br.pucrs.tcc2.reactive.domain.cpu.model.dto.CpuDto> cpu =
                Mono.fromSupplier(() -> Sha256Workload.execute(iterations));
        if (executionMode == ExecutionMode.BOUNDED_ELASTIC) cpu = cpu.subscribeOn(Schedulers.boundedElastic());
        return cpu.flatMap(cpuResult -> ioApiPort
                .execute(new IoInput(input.itemId(), input.runId(), input.requestId()))
                .map(ioResult -> new MixedDto(cpuResult, ioResult)));
    }

    private enum ExecutionMode {
        EVENT_LOOP, BOUNDED_ELASTIC;
        private static ExecutionMode parse(String value) {
            return switch (value) {
                case "event-loop" -> EVENT_LOOP;
                case "bounded-elastic" -> BOUNDED_ELASTIC;
                default -> throw new IllegalArgumentException(
                        "tcc.mixed.cpu-execution-mode must be event-loop or bounded-elastic");
            };
        }
    }
}
