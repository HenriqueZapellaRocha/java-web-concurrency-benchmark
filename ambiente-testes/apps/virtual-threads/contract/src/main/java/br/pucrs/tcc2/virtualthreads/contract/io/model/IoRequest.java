package br.pucrs.tcc2.virtualthreads.contract.io.model;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.UUID;

@Schema(name = "IoRequest", description = "Identifies the catalog item and the experimental request.")
public record IoRequest(
        @NotNull @Positive @Schema(example = "1", requiredMode = Schema.RequiredMode.REQUIRED) Long itemId,
        @NotNull @Schema(requiredMode = Schema.RequiredMode.REQUIRED) UUID runId,
        @NotNull @Schema(requiredMode = Schema.RequiredMode.REQUIRED) UUID requestId) {
}
