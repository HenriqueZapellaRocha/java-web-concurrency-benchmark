package br.pucrs.tcc2.reactive.contract.mixed;

import br.pucrs.tcc2.reactive.contract.config.exception.model.ErrorInfo;
import br.pucrs.tcc2.reactive.contract.mixed.mapper.MixedContractMapper;
import br.pucrs.tcc2.reactive.contract.mixed.model.MixedRequest;
import br.pucrs.tcc2.reactive.contract.mixed.model.MixedResponse;
import br.pucrs.tcc2.reactive.domain.mixed.port.api.MixedApiPort;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController @RequestMapping("/mixed") @Tag(name = "Mixed workload")
public class MixedController {
    private final MixedApiPort apiPort;
    private final MixedContractMapper mapper;
    public MixedController(MixedApiPort apiPort, MixedContractMapper mapper) { this.apiPort = apiPort; this.mapper = mapper; }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "executeMixed", summary = "Execute SHA-256, then read and record one catalog access", description = "CPU work precedes two reads and one transactional append-only write.")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "CPU work and access completed", content = @Content(schema = @Schema(implementation = MixedResponse.class))),
        @ApiResponse(responseCode = "400", description = "Invalid request", content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "404", description = "Item not found", content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "409", description = "Duplicate run/request pair", content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "500", description = "Unexpected failure", content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "503", description = "Database unavailable", content = @Content(schema = @Schema(implementation = ErrorInfo.class)))})
    public Mono<ResponseEntity<MixedResponse>> execute(@Valid @RequestBody MixedRequest request) {
        return apiPort.execute(mapper.toInput(request)).map(mapper::toResponse).map(ResponseEntity::ok);
    }
}
