package br.pucrs.tcc2.reactive.domain.mixed.model.input;
import java.util.UUID;
public record MixedInput(Long itemId, UUID runId, UUID requestId) { }
