import pytest

from nunchaku.utils import get_precision
from .utils import run_test


@pytest.mark.skipif(get_precision() == "fp4", reason="Blackwell GPUs. Skip tests for Turing.")
@pytest.mark.parametrize(
    "height,width,num_inference_steps,cpu_offload,i2f_mode,expected_lpips",
    [
        (1024, 1024, 50, True, None, 0.253),
        (1024, 1024, 50, True, "enabled", 0.258),
        (1024, 1024, 50, True, "always", 0.257),
    ],
)
def test_flux_dev(
    height: int, width: int, num_inference_steps: int, cpu_offload: bool, i2f_mode: str | None, expected_lpips: float
):
    run_test(
        precision=get_precision(),
        dtype="fp16",
        model_name="flux.1-dev",
        height=height,
        width=width,
        num_inference_steps=num_inference_steps,
        attention_impl="nunchaku-fp16",
        cpu_offload=cpu_offload,
        i2f_mode=i2f_mode,
        expected_lpips=expected_lpips,
    )
