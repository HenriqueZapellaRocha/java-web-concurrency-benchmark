package br.pucrs.tcc2.reactive.domain.io.model.dto;



public record IoDto(
        CatalogItemDto item,
        CategoryDto category,
        AccessEventDto event) {
}
