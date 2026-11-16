package br.pucrs.tcc2.virtualthreads.domain.mixed.model.dto;
import br.pucrs.tcc2.virtualthreads.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.IoDto;
public record MixedDto(CpuDto cpu, IoDto io) { }
