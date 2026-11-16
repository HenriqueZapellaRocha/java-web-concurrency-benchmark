package br.pucrs.tcc2.reactive.contract.io;

import br.pucrs.tcc2.reactive.contract.config.exception.model.ErrorInfo;
import br.pucrs.tcc2.reactive.contract.io.mapper.IoContractMapper;
import br.pucrs.tcc2.reactive.contract.io.model.IoRequest;
import br.pucrs.tcc2.reactive.contract.io.model.IoResponse;
import br.pucrs.tcc2.reactive.domain.io.port.api.IoApiPort;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/io")
@Tag(name = "I/O workload")
public class IoController {
    private final IoApiPort apiPort;
    private final IoContractMapper mapper;

    public IoController(IoApiPort apiPort, IoContractMapper mapper) {
        this.apiPort = apiPort;
        this.mapper = mapper;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "executeIo", summary = "Read a catalog item and category, then record one access",
            description = "Two separate reads and one append-only write. Success is returned after transaction commit.")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Access committed",
                content = @Content(schema = @Schema(implementation = IoResponse.class))),
        @ApiResponse(responseCode = "400", description = "Invalid request",
                content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "404", description = "Item not found",
                content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "409", description = "Duplicate run/request pair",
                content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "500", description = "Unexpected failure",
                content = @Content(schema = @Schema(implementation = ErrorInfo.class))),
        @ApiResponse(responseCode = "503", description = "Database unavailable",
                content = @Content(schema = @Schema(implementation = ErrorInfo.class)))
    })
    public Mono<ResponseEntity<IoResponse>> execute(@Valid @RequestBody IoRequest request) {
        return apiPort.execute(mapper.toInput(request))
                .map(mapper::toResponse)
                .map(ResponseEntity::ok);
    }
}
