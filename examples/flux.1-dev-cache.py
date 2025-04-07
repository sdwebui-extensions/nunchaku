import torch
from diffusers import FluxPipeline

from nunchaku import NunchakuFluxTransformer2dModel
from nunchaku.caching.diffusers_adapters import apply_cache_on_pipe
from nunchaku.utils import get_precision

precision = get_precision()  # auto-detect your precision is 'int4' or 'fp4' based on your GPU
transformer = NunchakuFluxTransformer2dModel.from_pretrained(f"mit-han-lab/svdq-{precision}-flux.1-dev")
pipeline = FluxPipeline.from_pretrained(
    "black-forest-labs/FLUX.1-dev", transformer=transformer, torch_dtype=torch.bfloat16
).to("cuda")
apply_cache_on_pipe(
    pipeline, residual_diff_threshold=0.12
)  # Set the first-block cache threshold. Increasing the value enhances speed at the cost of quality.
image = pipeline(["A cat holding a sign that says hello world"], num_inference_steps=50).images[0]
image.save(f"flux.1-dev-cache-{precision}.png")
