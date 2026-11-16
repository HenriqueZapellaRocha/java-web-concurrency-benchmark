package br.pucrs.tcc2.reactive.contract.io.model;

import java.math.BigDecimal;
import java.time.Instant;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CatalogItemResponse")
public record CatalogItemResponse(
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
