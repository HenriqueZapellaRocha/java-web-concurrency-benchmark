package br.pucrs.tcc2.mvc.common.exception;

public final class ExceptionMaker {
    private ExceptionMaker() {}

    public static ApplicationException itemNotFound(long itemId) {
        return new ApplicationException(ApplicationException.Kind.NOT_FOUND,
                "ITEM_NOT_FOUND", "Catalog item " + itemId + " was not found.");
    }

    public static ApplicationException inconsistentCatalog() {
        return new ApplicationException(ApplicationException.Kind.INCONSISTENT_CATALOG,
                "INCONSISTENT_CATALOG", "The catalog could not be read consistently.");
    }

    public static ApplicationException duplicateRequest() {
        return new ApplicationException(ApplicationException.Kind.CONFLICT,
                "DUPLICATE_REQUEST", "This request has already been recorded for this run.");
    }
}
