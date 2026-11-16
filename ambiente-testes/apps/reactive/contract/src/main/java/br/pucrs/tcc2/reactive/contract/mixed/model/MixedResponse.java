package br.pucrs.tcc2.reactive.contract.mixed.model;
import br.pucrs.tcc2.reactive.contract.cpu.model.CpuResponse;
import br.pucrs.tcc2.reactive.contract.io.model.IoResponse;
import io.swagger.v3.oas.annotations.media.Schema;
@Schema(name = "MixedResponse")
public record MixedResponse(CpuResponse cpu, IoResponse io) { }
