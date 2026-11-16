package br.pucrs.tcc2.virtualthreads.contract.io;

import br.pucrs.tcc2.virtualthreads.IoFixtures;
import br.pucrs.tcc2.virtualthreads.common.exception.ExceptionMaker;
import br.pucrs.tcc2.virtualthreads.contract.config.exception.ApiExceptionHandler;
import br.pucrs.tcc2.virtualthreads.contract.io.mapper.IoContractMapperImpl;
import br.pucrs.tcc2.virtualthreads.domain.io.port.api.IoApiPort;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = IoController.class, properties = {
        "spring.jackson.deserialization.fail-on-unknown-properties=true",
        "spring.jackson.deserialization.accept-float-as-int=false"
})
@ContextConfiguration(classes = IoController.class)
@Import({IoContractMapperImpl.class, ApiExceptionHandler.class})
class IoControllerTest {
    private static final String BODY = """
            {"itemId":1,"runId":"76ca367c-f087-4de1-bd2e-c4fe459699da",
             "requestId":"344e4a80-6f07-4bd7-bd9c-a090ece18c49"}
            """;
    @Autowired private MockMvc mvc;
    @MockitoBean private IoApiPort apiPort;

    @Test
    void mapsRequestAndAllThreeResponseObjects() throws Exception {
        when(apiPort.execute(any())).thenAnswer(call -> IoFixtures.output(call.getArgument(0)));
        mvc.perform(post("/io").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.item.id").value(1))
                .andExpect(jsonPath("$.item.categoryId").value(1))
                .andExpect(jsonPath("$.item.description").value("Item description"))
                .andExpect(jsonPath("$.item.price").value(12.34))
                .andExpect(jsonPath("$.category.active").value(true))
                .andExpect(jsonPath("$.category.description").value("Category description"))
                .andExpect(jsonPath("$.event.runId").value("76ca367c-f087-4de1-bd2e-c4fe459699da"))
                .andExpect(jsonPath("$.event.requestId").value("344e4a80-6f07-4bd7-bd9c-a090ece18c49"))
                .andExpect(jsonPath("$.event.eventType").value("ITEM_VIEW"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "{}", "null", "{", "{\"itemId\":0}",
            "{\"itemId\":1.5,\"runId\":\"76ca367c-f087-4de1-bd2e-c4fe459699da\",\"requestId\":\"344e4a80-6f07-4bd7-bd9c-a090ece18c49\"}",
            "{\"itemId\":1,\"runId\":\"invalid\",\"requestId\":null}",
            "{\"itemId\":-1,\"runId\":\"76ca367c-f087-4de1-bd2e-c4fe459699da\",\"requestId\":\"344e4a80-6f07-4bd7-bd9c-a090ece18c49\"}",
            "{\"itemId\":1,\"runId\":\"76ca367c-f087-4de1-bd2e-c4fe459699da\",\"requestId\":\"344e4a80-6f07-4bd7-bd9c-a090ece18c49\",\"extra\":true}"
    })
    void rejectsInvalidBodiesBeforeCallingDomain(String body) throws Exception {
        mvc.perform(post("/io").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code").value("INVALID_REQUEST"));
        verifyNoInteractions(apiPort);
    }

    @Test
    void preservesNotFoundAndConflictStatuses() throws Exception {
        when(apiPort.execute(any())).thenThrow(ExceptionMaker.itemNotFound(1), ExceptionMaker.duplicateRequest());
        mvc.perform(post("/io").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.errors[0].code").value("ITEM_NOT_FOUND"));
        mvc.perform(post("/io").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.errors[0].code").value("DUPLICATE_REQUEST"));
    }

    @Test
    void doesNotExposeInternalFailureDetails() throws Exception {
        when(apiPort.execute(any())).thenThrow(new IllegalStateException("private SQL details"));
        mvc.perform(post("/io").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.errors[0].message").value("The request could not be completed."));
    }

    @Test
    void databaseConnectionFailureReturnsServiceUnavailable() throws Exception {
        when(apiPort.execute(any())).thenThrow(
                new org.springframework.transaction.CannotCreateTransactionException("private connection details"));
        mvc.perform(post("/io").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.errors[0].code").value("DATABASE_UNAVAILABLE"))
                .andExpect(jsonPath("$.errors[0].message").value("The database is unavailable."));
    }

    @Test
    void preservesHttpMethodAndMediaTypeErrors() throws Exception {
        mvc.perform(get("/io")).andExpect(status().isMethodNotAllowed());
        mvc.perform(post("/io").contentType(MediaType.TEXT_PLAIN).content(BODY))
                .andExpect(status().isUnsupportedMediaType());
        verifyNoInteractions(apiPort);
    }
}
