#include "gemm.h"
#include "gemm88.h"
#include "flux.h"
#include "sana.h"
#include "ops.h"
#include "utils.h"
#include <torch/extension.h>

#include <pybind11/pybind11.h>

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    py::class_<QuantizedFluxModel>(m, "QuantizedFluxModel")
        .def(py::init<>())
        .def("init", &QuantizedFluxModel::init,
            py::arg("use_fp4"),
            py::arg("offload"),
            py::arg("bf16"),
            py::arg("deviceId")
        )
        .def("reset", &QuantizedFluxModel::reset)
        .def("load", &QuantizedFluxModel::load,
            py::arg("path"),
            py::arg("partial") = false
        )
        .def("loadDict", &QuantizedFluxModel::loadDict,
            py::arg("dict"),
            py::arg("partial") = false
        )
        .def("forward", &QuantizedFluxModel::forward,
            py::arg("hidden_states"),
            py::arg("encoder_hidden_states"),
            py::arg("temb"),
            py::arg("rotary_emb_img"),
            py::arg("rotary_emb_context"),
            py::arg("rotary_emb_single"),
            py::arg("controlnet_block_samples") = py::none(),
            py::arg("controlnet_single_block_samples") = py::none(),
            py::arg("skip_first_layer") = false
        )
        .def("forward_layer", &QuantizedFluxModel::forward_layer,
            py::arg("idx"),
            py::arg("hidden_states"),
            py::arg("encoder_hidden_states"),
            py::arg("temb"),
            py::arg("rotary_emb_img"),
            py::arg("rotary_emb_context"),
            py::arg("controlnet_block_samples") = py::none(),
            py::arg("controlnet_single_block_samples") = py::none()
        )
        .def("forward_single_layer", &QuantizedFluxModel::forward_single_layer)
        .def("startDebug", &QuantizedFluxModel::startDebug)
        .def("stopDebug", &QuantizedFluxModel::stopDebug)
        .def("getDebugResults", &QuantizedFluxModel::getDebugResults)
        .def("setLoraScale", &QuantizedFluxModel::setLoraScale)
        .def("setAttentionImpl", &QuantizedFluxModel::setAttentionImpl)
        .def("isBF16", &QuantizedFluxModel::isBF16)
    ;
    py::class_<QuantizedSanaModel>(m, "QuantizedSanaModel")
        .def(py::init<>())
        .def("init", &QuantizedSanaModel::init,
            py::arg("config"),
            py::arg("pag_layers"),
            py::arg("use_fp4"),
            py::arg("bf16"),
            py::arg("deviceId")
        )
        .def("reset", &QuantizedSanaModel::reset)
        .def("load", &QuantizedSanaModel::load,
            py::arg("path"),
            py::arg("partial") = false
        )
        .def("loadDict", &QuantizedSanaModel::loadDict,
            py::arg("dict"),
            py::arg("partial") = false
        )
        .def("forward", &QuantizedSanaModel::forward)
        .def("forward_layer", &QuantizedSanaModel::forward_layer)
        .def("startDebug", &QuantizedSanaModel::startDebug)
        .def("stopDebug", &QuantizedSanaModel::stopDebug)
        .def("getDebugResults", &QuantizedSanaModel::getDebugResults)
    ;
    py::class_<QuantizedGEMM>(m, "QuantizedGEMM")
        .def(py::init<>())
        .def("init", &QuantizedGEMM::init)
        .def("reset", &QuantizedGEMM::reset)
        .def("load", &QuantizedGEMM::load)
        .def("forward", &QuantizedGEMM::forward)
        .def("quantize", &QuantizedGEMM::quantize)
        .def("startDebug", &QuantizedGEMM::startDebug)
        .def("stopDebug", &QuantizedGEMM::stopDebug)
        .def("getDebugResults", &QuantizedGEMM::getDebugResults)
    ;
    py::class_<QuantizedGEMM88>(m, "QuantizedGEMM88")
        .def(py::init<>())
        .def("init", &QuantizedGEMM88::init)
        .def("reset", &QuantizedGEMM88::reset)
        .def("load", &QuantizedGEMM88::load)
        .def("forward", &QuantizedGEMM88::forward)
        .def("startDebug", &QuantizedGEMM88::startDebug)
        .def("stopDebug", &QuantizedGEMM88::stopDebug)
        .def("getDebugResults", &QuantizedGEMM88::getDebugResults)
    ;

    m.def_submodule("ops")
        .def("gemm_w4a4", nunchaku::ops::gemm_w4a4)
        .def("attention_fp16", nunchaku::ops::attention_fp16)
        .def("gemm_awq", nunchaku::ops::gemm_awq)
        .def("gemv_awq", nunchaku::ops::gemv_awq)

        .def("test_rmsnorm_rope", nunchaku::ops::test_rmsnorm_rope)
        .def("test_pack_qkv", nunchaku::ops::test_pack_qkv)
    ;

    m.def_submodule("utils")
        .def("set_log_level", [](const std::string &level) {
            spdlog::set_level(spdlog::level::from_str(level));
        })
        .def("set_cuda_stack_limit", nunchaku::utils::set_cuda_stack_limit)
        .def("disable_memory_auto_release", nunchaku::utils::disable_memory_auto_release)
        .def("trim_memory", nunchaku::utils::trim_memory)
        .def("set_faster_i2f_mode", nunchaku::utils::set_faster_i2f_mode)
    ;
}
