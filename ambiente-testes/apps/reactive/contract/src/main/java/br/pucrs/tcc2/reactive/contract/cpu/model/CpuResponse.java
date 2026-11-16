package br.pucrs.tcc2.reactive.contract.cpu.model;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CpuResponse")
public record CpuResponse(int iterations, String digest) {
}
