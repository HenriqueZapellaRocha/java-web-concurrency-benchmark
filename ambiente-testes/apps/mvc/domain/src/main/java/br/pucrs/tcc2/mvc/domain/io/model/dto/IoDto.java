package br.pucrs.tcc2.mvc.domain.io.model.dto;



public record IoDto(
        CatalogItemDto item,
        CategoryDto category,
        AccessEventDto event) {
}
