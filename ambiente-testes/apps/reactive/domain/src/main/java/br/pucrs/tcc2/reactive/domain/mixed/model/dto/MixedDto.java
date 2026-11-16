package br.pucrs.tcc2.reactive.domain.mixed.model.dto;
import br.pucrs.tcc2.reactive.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.IoDto;
public record MixedDto(CpuDto cpu, IoDto io) { }
