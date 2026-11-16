package br.pucrs.tcc2.mvc.contract.mixed.model;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.UUID;

@Schema(name = "MixedRequest", description = "Identifies the catalog item and the experimental request.")
public record MixedRequest(
        @NotNull @Positive @Schema(example = "1", requiredMode = Schema.RequiredMode.REQUIRED) Long itemId,
        @NotNull @Schema(requiredMode = Schema.RequiredMode.REQUIRED) UUID runId,
        @NotNull @Schema(requiredMode = Schema.RequiredMode.REQUIRED) UUID requestId) {
}
