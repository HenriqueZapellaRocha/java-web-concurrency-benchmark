package br.pucrs.tcc2.reactive.domain.cpu.port.api;

import br.pucrs.tcc2.reactive.domain.cpu.model.dto.CpuDto;
import reactor.core.publisher.Mono;

public interface CpuApiPort {
    Mono<CpuDto> execute();
}
