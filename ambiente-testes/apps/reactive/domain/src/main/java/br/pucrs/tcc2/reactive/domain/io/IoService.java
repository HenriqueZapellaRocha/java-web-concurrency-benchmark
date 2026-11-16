package br.pucrs.tcc2.reactive.domain.io;

import br.pucrs.tcc2.reactive.common.exception.ExceptionMaker;
import br.pucrs.tcc2.reactive.domain.io.model.dto.IoDto;
import br.pucrs.tcc2.reactive.domain.io.model.input.AccessEventInput;
import br.pucrs.tcc2.reactive.domain.io.model.input.IoInput;
import br.pucrs.tcc2.reactive.domain.io.port.api.IoApiPort;
import br.pucrs.tcc2.reactive.domain.io.port.spi.IoSpiPort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class IoService implements IoApiPort {
    private final IoSpiPort spiPort;

    public IoService(IoSpiPort spiPort) {
        this.spiPort = spiPort;
    }

    @Override
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Mono<IoDto> execute(IoInput input) {
        return Mono.defer(spiPort::applyDatabaseDelay)
                .then(Mono.defer(() -> spiPort.findItemById(input.itemId())))
                .switchIfEmpty(Mono.defer(() -> Mono.error(ExceptionMaker.itemNotFound(input.itemId()))))
                .flatMap(item -> spiPort.findCategoryById(item.categoryId())
                        .switchIfEmpty(Mono.defer(() -> Mono.error(ExceptionMaker.inconsistentCatalog())))
                        .flatMap(category -> spiPort.appendEvent(new AccessEventInput(
                                        item.id(), input.runId(), input.requestId(), "ITEM_VIEW"))
                                .map(event -> new IoDto(item, category, event))));
    }
}
