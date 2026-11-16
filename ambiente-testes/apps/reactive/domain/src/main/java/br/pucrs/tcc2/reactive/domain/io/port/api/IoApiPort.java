package br.pucrs.tcc2.reactive.domain.io.port.api;

import br.pucrs.tcc2.reactive.domain.io.model.dto.IoDto;
import br.pucrs.tcc2.reactive.domain.io.model.input.IoInput;
import reactor.core.publisher.Mono;

public interface IoApiPort {
    Mono<IoDto> execute(IoInput input);
}
