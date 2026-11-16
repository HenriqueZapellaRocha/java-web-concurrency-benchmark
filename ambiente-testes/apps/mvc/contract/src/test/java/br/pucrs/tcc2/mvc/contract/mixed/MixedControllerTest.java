package br.pucrs.tcc2.mvc.contract.mixed;

import br.pucrs.tcc2.mvc.IoFixtures;
import br.pucrs.tcc2.mvc.contract.config.exception.ApiExceptionHandler;
import br.pucrs.tcc2.mvc.contract.cpu.mapper.CpuContractMapperImpl;
import br.pucrs.tcc2.mvc.contract.io.mapper.IoContractMapperImpl;
import br.pucrs.tcc2.mvc.contract.mixed.mapper.MixedContractMapperImpl;
import br.pucrs.tcc2.mvc.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.mvc.domain.io.model.input.IoInput;
import br.pucrs.tcc2.mvc.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.mvc.domain.mixed.model.input.MixedInput;
import br.pucrs.tcc2.mvc.domain.mixed.port.api.MixedApiPort;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = MixedController.class, properties = {
        "spring.jackson.deserialization.fail-on-unknown-properties=true",
        "spring.jackson.deserialization.accept-float-as-int=false"})
@ContextConfiguration(classes = MixedController.class)
@Import({MixedContractMapperImpl.class, CpuContractMapperImpl.class, IoContractMapperImpl.class,
        ApiExceptionHandler.class})
class MixedControllerTest {
    private static final String BODY = """
            {"itemId":1,"runId":"76ca367c-f087-4de1-bd2e-c4fe459699da",
             "requestId":"344e4a80-6f07-4bd7-bd9c-a090ece18c49"}
            """;
    @Autowired private MockMvc mvc;
    @MockitoBean private MixedApiPort apiPort;

    @Test
    void returnsCpuAndIoResults() throws Exception {
        when(apiPort.execute(any())).thenAnswer(call -> output(call.getArgument(0)));
        mvc.perform(post("/mixed").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.cpu.iterations").value(2))
                .andExpect(jsonPath("$.cpu.digest").value("digest"))
                .andExpect(jsonPath("$.io.item.id").value(1))
                .andExpect(jsonPath("$.io.category.id").value(1))
                .andExpect(jsonPath("$.io.event.eventType").value("ITEM_VIEW"));
    }

    @Test
    void rejectsInvalidBodyBeforeDomain() throws Exception {
        mvc.perform(post("/mixed").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code").value("INVALID_REQUEST"));
        verifyNoInteractions(apiPort);
    }

    private MixedDto output(MixedInput input) {
        var ioInput = new IoInput(input.itemId(), input.runId(), input.requestId());
        return new MixedDto(new CpuDto(2, "digest"), IoFixtures.output(ioInput));
    }
}
