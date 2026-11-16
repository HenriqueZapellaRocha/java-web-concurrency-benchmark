package br.pucrs.tcc2.mvc.domain.io.model.dto;

import java.time.Instant;

public record CategoryDto(
        Long id,
        String name,
        String slug,
        String description,
        Integer displayOrder,
        boolean active,
        Instant createdAt,
        Instant updatedAt) {
}
