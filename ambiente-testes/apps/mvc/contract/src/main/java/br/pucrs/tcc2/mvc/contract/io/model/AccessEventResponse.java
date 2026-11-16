package br.pucrs.tcc2.mvc.contract.io.model;

import java.time.Instant;
import java.util.UUID;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "AccessEventResponse")
public record AccessEventResponse(
        Long id,
        Long itemId,
        UUID runId,
        UUID requestId,
        String eventType,
        Instant createdAt) {
}
