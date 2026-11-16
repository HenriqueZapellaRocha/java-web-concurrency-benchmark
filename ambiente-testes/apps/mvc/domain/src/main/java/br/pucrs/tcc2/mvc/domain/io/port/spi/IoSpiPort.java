package br.pucrs.tcc2.mvc.domain.io.port.spi;

import br.pucrs.tcc2.mvc.domain.io.model.dto.AccessEventDto;
import br.pucrs.tcc2.mvc.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.mvc.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.mvc.domain.io.model.input.AccessEventInput;
import java.util.Optional;

public interface IoSpiPort {
    void applyDatabaseDelay();
    Optional<CatalogItemDto> findItemById(long itemId);
    Optional<CategoryDto> findCategoryById(long categoryId);
    AccessEventDto appendEvent(AccessEventInput input);
}
