package br.pucrs.tcc2.reactive.infrastructure.io.model;

import java.time.Instant;

public record CategoryEntity(
        Long id,
        String name,
        String slug,
        String description,
        Integer displayOrder,
        boolean active,
        Instant createdAt,
        Instant updatedAt) {
}
