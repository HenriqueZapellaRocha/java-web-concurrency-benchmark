package br.pucrs.tcc2.mvc.contract.io.model;

import java.time.Instant;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CategoryResponse")
public record CategoryResponse(
        Long id,
        String name,
        String slug,
        String description,
        Integer displayOrder,
        boolean active,
        Instant createdAt,
        Instant updatedAt) {
}
