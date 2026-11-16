package br.pucrs.tcc2.virtualthreads.domain.io.model.dto;

import java.time.Instant;
import java.util.UUID;

public record AccessEventDto(
        Long id,
        Long itemId,
        UUID runId,
        UUID requestId,
        String eventType,
        Instant createdAt) {
}
