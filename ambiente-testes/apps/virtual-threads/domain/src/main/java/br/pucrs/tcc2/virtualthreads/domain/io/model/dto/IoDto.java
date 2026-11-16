package br.pucrs.tcc2.virtualthreads.domain.io.model.dto;



public record IoDto(
        CatalogItemDto item,
        CategoryDto category,
        AccessEventDto event) {
}
