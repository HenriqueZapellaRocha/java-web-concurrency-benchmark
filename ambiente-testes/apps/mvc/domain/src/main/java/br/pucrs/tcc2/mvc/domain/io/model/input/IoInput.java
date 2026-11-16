package br.pucrs.tcc2.mvc.domain.io.model.input;

import java.util.UUID;

public record IoInput(
        Long itemId,
        UUID runId,
        UUID requestId) {
}
