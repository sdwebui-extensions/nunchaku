# This caching functionality is largely brought from https://github.com/chengzeyi/ParaAttention/src/para_attn/first_block_cache/

import contextlib
import dataclasses
from collections import defaultdict
from typing import DefaultDict, Dict, Optional

import torch
from torch import nn


@dataclasses.dataclass
class CacheContext:
    buffers: Dict[str, torch.Tensor] = dataclasses.field(default_factory=dict)
    incremental_name_counters: DefaultDict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))

    def get_incremental_name(self, name=None):
        if name is None:
            name = "default"
        idx = self.incremental_name_counters[name]
        self.incremental_name_counters[name] += 1
        return f"{name}_{idx}"

    def reset_incremental_name(self):
        self.incremental_name_counters.clear()

    # @torch.compiler.disable # This is a torchscript feature
    def get_buffer(self, name=str):
        return self.buffers.get(name)

    def set_buffer(self, name, buffer):
        self.buffers[name] = buffer

    def clear_buffers(self):
        self.buffers.clear()


@torch.compiler.disable
def get_buffer(name):
    cache_context = get_current_cache_context()
    assert cache_context is not None, "cache_context must be set before"
    return cache_context.get_buffer(name)


@torch.compiler.disable
def set_buffer(name, buffer):
    cache_context = get_current_cache_context()
    assert cache_context is not None, "cache_context must be set before"
    cache_context.set_buffer(name, buffer)


_current_cache_context = None


def create_cache_context():
    return CacheContext()


def get_current_cache_context():
    return _current_cache_context


@contextlib.contextmanager
def cache_context(cache_context):
    global _current_cache_context
    old_cache_context = _current_cache_context
    _current_cache_context = cache_context
    try:
        yield
    finally:
        _current_cache_context = old_cache_context


@torch.compiler.disable
def are_two_tensors_similar(t1, t2, *, threshold, parallelized=False):
    mean_diff = (t1 - t2).abs().mean()
    mean_t1 = t1.abs().mean()
    diff = mean_diff / mean_t1
    return diff.item() < threshold


@torch.compiler.disable
def apply_prev_hidden_states_residual(
    hidden_states: torch.Tensor, encoder_hidden_states: Optional[torch.Tensor] = None
) -> tuple[torch.Tensor, torch.Tensor]:
    hidden_states_residual = get_buffer("hidden_states_residual")
    assert hidden_states_residual is not None, "hidden_states_residual must be set before"
    hidden_states = hidden_states_residual + hidden_states

    hidden_states = hidden_states.contiguous()
    if encoder_hidden_states is not None:
        encoder_hidden_states_residual = get_buffer("encoder_hidden_states_residual")
        assert encoder_hidden_states_residual is not None, "encoder_hidden_states_residual must be set before"
        encoder_hidden_states = encoder_hidden_states_residual + encoder_hidden_states
        encoder_hidden_states = encoder_hidden_states.contiguous()

    return hidden_states, encoder_hidden_states


@torch.compiler.disable
def get_can_use_cache(first_hidden_states_residual, threshold, parallelized=False):
    prev_first_hidden_states_residual = get_buffer("first_hidden_states_residual")
    can_use_cache = prev_first_hidden_states_residual is not None and are_two_tensors_similar(
        prev_first_hidden_states_residual,
        first_hidden_states_residual,
        threshold=threshold,
        parallelized=parallelized,
    )
    return can_use_cache


class SanaCachedTransformerBlocks(nn.Module):
    def __init__(
        self,
        *,
        transformer=None,
        residual_diff_threshold,
        verbose: bool = False,
    ):
        super().__init__()
        self.transformer = transformer
        self.transformer_blocks = transformer.transformer_blocks
        self.residual_diff_threshold = residual_diff_threshold
        self.verbose = verbose

    def forward(
        self,
        hidden_states,
        attention_mask,
        encoder_hidden_states,
        encoder_attention_mask=None,
        timestep=None,
        post_patch_height=None,
        post_patch_width=None,
    ):
        batch_size = hidden_states.shape[0]
        if self.residual_diff_threshold <= 0.0 or batch_size > 2:
            if batch_size > 2:
                print("Batch size > 2 (for SANA CFG)" " currently not supported")

            first_transformer_block = self.transformer_blocks[0]
            hidden_states = first_transformer_block(
                hidden_states=hidden_states,
                attention_mask=attention_mask,
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                timestep=timestep,
                height=post_patch_height,
                width=post_patch_width,
                skip_first_layer=False,
            )
            return hidden_states

        original_hidden_states = hidden_states
        first_transformer_block = self.transformer_blocks[0]

        hidden_states = first_transformer_block.forward_layer_at(
            0,
            hidden_states=hidden_states,
            attention_mask=attention_mask,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            timestep=timestep,
            height=post_patch_height,
            width=post_patch_width,
        )
        first_hidden_states_residual = hidden_states - original_hidden_states
        del original_hidden_states

        can_use_cache = get_can_use_cache(
            first_hidden_states_residual,
            threshold=self.residual_diff_threshold,
            parallelized=self.transformer is not None and getattr(self.transformer, "_is_parallelized", False),
        )

        torch._dynamo.graph_break()
        if can_use_cache:
            del first_hidden_states_residual
            if self.verbose:
                print("Cache hit!!!")
            hidden_states, _ = apply_prev_hidden_states_residual(hidden_states, None)
        else:
            if self.verbose:
                print("Cache miss!!!")
            set_buffer("first_hidden_states_residual", first_hidden_states_residual)
            del first_hidden_states_residual

            hidden_states, hidden_states_residual = self.call_remaining_transformer_blocks(
                hidden_states=hidden_states,
                attention_mask=attention_mask,
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=encoder_attention_mask,
                timestep=timestep,
                post_patch_height=post_patch_height,
                post_patch_width=post_patch_width,
            )
            set_buffer("hidden_states_residual", hidden_states_residual)
        torch._dynamo.graph_break()

        return hidden_states

    def call_remaining_transformer_blocks(
        self,
        hidden_states,
        attention_mask,
        encoder_hidden_states,
        encoder_attention_mask=None,
        timestep=None,
        post_patch_height=None,
        post_patch_width=None,
    ):
        first_transformer_block = self.transformer_blocks[0]
        original_hidden_states = hidden_states
        hidden_states = first_transformer_block(
            hidden_states=hidden_states,
            attention_mask=attention_mask,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            timestep=timestep,
            height=post_patch_height,
            width=post_patch_width,
            skip_first_layer=True,
        )
        hidden_states_residual = hidden_states - original_hidden_states

        return hidden_states, hidden_states_residual


class FluxCachedTransformerBlocks(nn.Module):
    def __init__(
        self,
        *,
        transformer=None,
        residual_diff_threshold,
        return_hidden_states_first=True,
        return_hidden_states_only=False,
        verbose: bool = False,
    ):
        super().__init__()
        self.transformer = transformer
        self.transformer_blocks = transformer.transformer_blocks
        self.single_transformer_blocks = transformer.single_transformer_blocks
        self.residual_diff_threshold = residual_diff_threshold
        self.return_hidden_states_first = return_hidden_states_first
        self.return_hidden_states_only = return_hidden_states_only
        self.verbose = verbose

    def forward(self, hidden_states, encoder_hidden_states, *args, **kwargs):
        batch_size = hidden_states.shape[0]
        if self.residual_diff_threshold <= 0.0 or batch_size > 1:
            if batch_size > 1:
                print("Batch size > 1 currently not supported")

            first_transformer_block = self.transformer_blocks[0]
            encoder_hidden_states, hidden_states = first_transformer_block(
                hidden_states=hidden_states, encoder_hidden_states=encoder_hidden_states, *args, **kwargs
            )

            return (
                hidden_states
                if self.return_hidden_states_only
                else (
                    (hidden_states, encoder_hidden_states)
                    if self.return_hidden_states_first
                    else (encoder_hidden_states, hidden_states)
                )
            )

        original_hidden_states = hidden_states
        first_transformer_block = self.transformer_blocks[0]
        encoder_hidden_states, hidden_states = first_transformer_block.forward_layer_at(
            0, hidden_states, encoder_hidden_states, *args, **kwargs
        )

        first_hidden_states_residual = hidden_states - original_hidden_states
        del original_hidden_states

        can_use_cache = get_can_use_cache(
            first_hidden_states_residual,
            threshold=self.residual_diff_threshold,
            parallelized=self.transformer is not None and getattr(self.transformer, "_is_parallelized", False),
        )

        torch._dynamo.graph_break()
        if can_use_cache:
            del first_hidden_states_residual
            if self.verbose:
                print("Cache hit!!!")
            hidden_states, encoder_hidden_states = apply_prev_hidden_states_residual(
                hidden_states, encoder_hidden_states
            )
        else:
            if self.verbose:
                print("Cache miss!!!")
            set_buffer("first_hidden_states_residual", first_hidden_states_residual)
            del first_hidden_states_residual
            (
                hidden_states,
                encoder_hidden_states,
                hidden_states_residual,
                encoder_hidden_states_residual,
            ) = self.call_remaining_transformer_blocks(hidden_states, encoder_hidden_states, *args, **kwargs)
            set_buffer("hidden_states_residual", hidden_states_residual)
            set_buffer("encoder_hidden_states_residual", encoder_hidden_states_residual)
        torch._dynamo.graph_break()

        return (
            hidden_states
            if self.return_hidden_states_only
            else (
                (hidden_states, encoder_hidden_states)
                if self.return_hidden_states_first
                else (encoder_hidden_states, hidden_states)
            )
        )

    def call_remaining_transformer_blocks(self, hidden_states, encoder_hidden_states, *args, **kwargs):
        first_transformer_block = self.transformer_blocks[0]
        original_hidden_states = hidden_states
        original_encoder_hidden_states = encoder_hidden_states
        encoder_hidden_states, hidden_states = first_transformer_block.forward(
            hidden_states=hidden_states,
            encoder_hidden_states=encoder_hidden_states,
            skip_first_layer=True,
            *args,
            **kwargs,
        )

        hidden_states = hidden_states.contiguous()
        encoder_hidden_states = encoder_hidden_states.contiguous()

        hidden_states_residual = hidden_states - original_hidden_states
        encoder_hidden_states_residual = encoder_hidden_states - original_encoder_hidden_states

        return hidden_states, encoder_hidden_states, hidden_states_residual, encoder_hidden_states_residual
