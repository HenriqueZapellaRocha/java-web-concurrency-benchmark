package br.pucrs.tcc2.reactive.infrastructure.io.model;

import java.math.BigDecimal;
import java.time.Instant;

public record CatalogItemEntity(
        Long id,
        Long categoryId,
        String sku,
        String name,
        String description,
        String brand,
        String model,
        BigDecimal price,
        String currency,
        Integer weightGrams,
        String status,
        Instant createdAt,
        Instant updatedAt) {
}
