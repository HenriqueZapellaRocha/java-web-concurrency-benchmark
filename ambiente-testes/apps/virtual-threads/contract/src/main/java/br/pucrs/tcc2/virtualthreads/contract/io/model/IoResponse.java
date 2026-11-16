package br.pucrs.tcc2.virtualthreads.contract.io.model;


import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "IoResponse")
public record IoResponse(
        CatalogItemResponse item,
        CategoryResponse category,
        AccessEventResponse event) {
}
