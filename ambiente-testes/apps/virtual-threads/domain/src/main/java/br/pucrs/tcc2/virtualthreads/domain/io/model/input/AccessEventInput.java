package br.pucrs.tcc2.virtualthreads.domain.io.model.input;

import java.util.UUID;

public record AccessEventInput(
        Long itemId,
        UUID runId,
        UUID requestId,
        String eventType) {
}
