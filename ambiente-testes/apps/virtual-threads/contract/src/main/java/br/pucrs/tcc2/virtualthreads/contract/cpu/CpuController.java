package br.pucrs.tcc2.virtualthreads.contract.cpu;

import br.pucrs.tcc2.virtualthreads.contract.cpu.mapper.CpuContractMapper;
import br.pucrs.tcc2.virtualthreads.contract.cpu.model.CpuResponse;
import br.pucrs.tcc2.virtualthreads.domain.cpu.port.api.CpuApiPort;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/cpu")
public class CpuController {
    private final CpuApiPort apiPort;
    private final CpuContractMapper mapper;

    public CpuController(CpuApiPort apiPort, CpuContractMapper mapper) {
        this.apiPort = apiPort;
        this.mapper = mapper;
    }

    @PostMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "executeCpu", summary = "Execute the deterministic PBKDF2 login workload")
    @ApiResponse(responseCode = "200", description = "Workload completed",
            content = @Content(schema = @Schema(implementation = CpuResponse.class)))
    public ResponseEntity<CpuResponse> execute() {
        return ResponseEntity.ok(mapper.toResponse(apiPort.execute()));
    }
}
