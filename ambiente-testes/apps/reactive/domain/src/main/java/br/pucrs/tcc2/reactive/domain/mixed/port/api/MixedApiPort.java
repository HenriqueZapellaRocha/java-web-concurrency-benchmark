package br.pucrs.tcc2.reactive.domain.mixed.port.api;
import br.pucrs.tcc2.reactive.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.reactive.domain.mixed.model.input.MixedInput;
import reactor.core.publisher.Mono;
public interface MixedApiPort { Mono<MixedDto> execute(MixedInput input); }
