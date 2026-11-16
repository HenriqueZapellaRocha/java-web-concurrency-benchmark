package br.pucrs.tcc2.reactive.domain.io.model.dto;

import java.math.BigDecimal;
import java.time.Instant;

public record CatalogItemDto(
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
