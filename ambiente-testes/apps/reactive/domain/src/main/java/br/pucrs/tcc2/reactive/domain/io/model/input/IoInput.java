package br.pucrs.tcc2.reactive.domain.io.model.input;

import java.util.UUID;

public record IoInput(
        Long itemId,
        UUID runId,
        UUID requestId) {
}
