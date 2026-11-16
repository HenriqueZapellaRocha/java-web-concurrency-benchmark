package br.pucrs.tcc2.reactive;

import br.pucrs.tcc2.reactive.domain.io.model.dto.AccessEventDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.IoDto;
import br.pucrs.tcc2.reactive.domain.io.model.input.IoInput;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public final class IoFixtures {
    public static final Instant TIME = Instant.parse("2026-01-01T00:00:00Z");

    private IoFixtures() {}

    public static IoInput input() {
        return new IoInput(1L, UUID.randomUUID(), UUID.randomUUID());
    }

    public static CatalogItemDto item() {
        return new CatalogItemDto(1L, 1L, "SKU-1", "Item 1", "Item description", "Brand", "Model",
                new BigDecimal("12.34"), "BRL", 100, "ACTIVE", TIME, TIME);
    }

    public static CategoryDto category() {
        return new CategoryDto(1L, "Category 1", "category-1", "Category description", 0, true, TIME, TIME);
    }

    public static IoDto output(IoInput input) {
        return new IoDto(item(), category(), new AccessEventDto(1L, input.itemId(), input.runId(),
                input.requestId(), "ITEM_VIEW", TIME));
    }
}
