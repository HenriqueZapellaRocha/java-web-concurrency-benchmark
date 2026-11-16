package br.pucrs.tcc2.virtualthreads.contract.cpu;

import br.pucrs.tcc2.virtualthreads.contract.cpu.mapper.CpuContractMapperImpl;
import br.pucrs.tcc2.virtualthreads.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.virtualthreads.domain.cpu.port.api.CpuApiPort;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CpuController.class)
@ContextConfiguration(classes = CpuController.class)
@Import(CpuContractMapperImpl.class)
class CpuControllerTest {
    @org.springframework.beans.factory.annotation.Autowired private MockMvc mvc;
    @MockitoBean private CpuApiPort apiPort;

    @Test
    void returnsIterationsAndDigest() throws Exception {
        when(apiPort.execute()).thenReturn(new CpuDto(2, "digest"));
        mvc.perform(post("/cpu"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.iterations").value(2))
                .andExpect(jsonPath("$.digest").value("digest"));
    }
}
