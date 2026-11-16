package br.pucrs.tcc2.reactive.domain.io.port.spi;

import br.pucrs.tcc2.reactive.domain.io.model.dto.AccessEventDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.reactive.domain.io.model.input.AccessEventInput;
import reactor.core.publisher.Mono;

public interface IoSpiPort {
    Mono<Void> applyDatabaseDelay();
    Mono<CatalogItemDto> findItemById(long itemId);
    Mono<CategoryDto> findCategoryById(long categoryId);
    Mono<AccessEventDto> appendEvent(AccessEventInput input);
}
