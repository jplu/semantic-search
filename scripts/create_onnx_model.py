import argparse
import logging
import pathlib

from collections import OrderedDict
from typing import Dict, Mapping

import torch

from nni.algorithms.compression.pytorch.pruning import TransformerHeadPruner
from onnxruntime.transformers.fusion_options import FusionOptions
from onnxruntime.transformers.optimizer import optimize_model
from onnxruntime.quantization import quantize_dynamic, QuantType
from transformers import BertModel, AutoTokenizer, AutoConfig, AutoModelForSequenceClassification, BertConfig
from transformers.onnx import OnnxConfig, export, validate_model_outputs
from transformers.utils.dummy_pt_objects import AutoModel


class Encoder(BertModel):
    def __init__(self, config: BertConfig):
        super().__init__(config)

        self.sentence_embedding = torch.nn.Identity()
    
    def forward(self, input_ids: torch.LongTensor, attention_mask: torch.FloatTensor, token_type_ids: torch.LongTensor) -> Dict[str, torch.FloatTensor]:
        token_embeddings = super().forward(
            input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
        )[0]

        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size())
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        ebds = self.sentence_embedding(sum_embeddings / sum_mask)

        return {"sentence_embedding": torch.nn.functional.normalize(ebds, p=2, dim=1)}


class EncoderOnnxConfig(OnnxConfig):
    @property
    def inputs(self) -> Mapping[str, Mapping[int, str]]:
        return OrderedDict(
            [
                ("input_ids", {0: "batch", 1: "sequence"}),
                ("attention_mask", {0: "batch", 1: "sequence"}),
                ("token_type_ids", {0: "batch", 1: "sequence"}),
            ]
        )

    @property
    def outputs(self) -> Mapping[str, Mapping[int, str]]:
        return OrderedDict([("sentence_embedding", {0: "batch"})])


class RerankOnnxConfig(OnnxConfig):
    @property
    def inputs(self) -> Mapping[str, Mapping[int, str]]:
        return OrderedDict(
            [
                ("input_ids", {0: "batch", 1: "sequence"}),
                ("attention_mask", {0: "batch", 1: "sequence"}),
                ("token_type_ids", {0: "batch", 1: "sequence"}),
            ]
        )

    @property
    def outputs(self) -> Mapping[str, Mapping[int, str]]:
        return OrderedDict([("logits", {0: "batch"})])


def prune_encoder(model_name: str) -> Encoder:
    config = AutoConfig.from_pretrained(model_name)
    model = Encoder(config=config).from_pretrained(model_name)
    attention_name_groups = list(
        zip(
            ["encoder.layer.{}.attention.self.query".format(i) for i in range(config.num_hidden_layers)],
            ["encoder.layer.{}.attention.self.key".format(i) for i in range(config.num_hidden_layers)],
            ["encoder.layer.{}.attention.self.value".format(i) for i in range(config.num_hidden_layers)],
            ["encoder.layer.{}.attention.output.dense".format(i) for i in range(config.num_hidden_layers)]
        )
    )
    half = config.num_hidden_layers // 2
    kwargs = {
        "head_hidden_dim": 64,
        "attention_name_groups": attention_name_groups,
    }
    config_list = [{
            "sparsity": 0.5,
            "op_types": ["Linear"],
            "op_names": [x for layer in attention_name_groups[:half] for x in layer]
        }, {
            "sparsity": 0.25,
            "op_types": ["Linear"],
            "op_names": [x for layer in attention_name_groups[half:] for x in layer]
        }
    ]

    pruner = TransformerHeadPruner(model, config_list, **kwargs)
    pruner.compress()

    speedup_rules = {}

    for group_idx, group in enumerate(pruner.attention_name_groups):
        layer_idx = None

        for part in group[0].split("."):
            try:
                layer_idx = int(part)
                break
            except:
                continue

        if layer_idx is not None:
            speedup_rules[layer_idx] = pruner.pruned_heads[group_idx]

    pruner._unwrap_model()

    for i, layer in enumerate(model.encoder.layer):
        model.encoder.layer[i].attention.prune_heads(speedup_rules[i])

    model.config.pruned_heads =  {key: list(val) for key, val in pruner.pruned_heads.items()}

    return model


def convert_to_onnx(model: AutoModel, output: pathlib.Path, is_encoder: bool) -> pathlib.Path:
    tokenizer = AutoTokenizer.from_pretrained(model.config._name_or_path)

    if is_encoder:
        onnx_config = EncoderOnnxConfig(model.config)
        output = output / "encoder"
    else:
        onnx_config = RerankOnnxConfig(model.config)
        output = output / "rerank"

    output.mkdir(parents=True, exist_ok=True)

    output = output / "model.onnx"

    _, onnx_outputs = export(tokenizer, model, onnx_config, 12, output)

    validate_model_outputs(onnx_config, tokenizer, model, output, onnx_outputs, 1e-4)

    return output


def optimizing_model(onnx_model: pathlib.Path) -> pathlib.Path:
    optimization_options = FusionOptions('bert')

    optimization_options.enable_embed_layer_norm = False

    optimizer = optimize_model(onnx_model.as_posix(),
                            "bert",
                            0,
                            0,
                            opt_level=2,
                            optimization_options=optimization_options,
                            use_gpu=False,
                            only_onnxruntime=True)
    
    output = onnx_model.parent / "model_opt.onnx"

    optimizer.save_model_to_file(output.as_posix(), False)

    return output


def quantizing_model(optimized_onnx_model: pathlib.Path):
    output = optimized_onnx_model.parent / "model_opt_quant.onnx"

    quantize_dynamic(optimized_onnx_model.as_posix(), output.as_posix(), weight_type=QuantType.QInt8, reduce_range=True)


def prune_rerank(model_name: str) -> AutoModelForSequenceClassification:
    config = AutoConfig.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)

    attention_name_groups = list(
        zip(
            [config.model_type + ".encoder.layer.{}.attention.self.query".format(i) for i in range(config.num_hidden_layers)],
            [config.model_type + ".encoder.layer.{}.attention.self.key".format(i) for i in range(config.num_hidden_layers)],
            [config.model_type + ".encoder.layer.{}.attention.self.value".format(i) for i in range(config.num_hidden_layers)],
            [config.model_type + ".encoder.layer.{}.attention.output.dense".format(i) for i in range(config.num_hidden_layers)]
        )
    )
    kwargs = {
        "head_hidden_dim": 64,
        "attention_name_groups": attention_name_groups,
    }
    config_list = [{
            "sparsity": 0.5,
            "op_types": ["Linear"],
            "op_names": [x for layer in attention_name_groups[:3] for x in layer]
        }, {
            "sparsity": 0.25,
            "op_types": ["Linear"],
            "op_names": [x for layer in attention_name_groups[3:] for x in layer]
        }
    ]

    pruner = TransformerHeadPruner(model, config_list, **kwargs)

    pruner.compress()

    speedup_rules = {}

    for group_idx, group in enumerate(pruner.attention_name_groups):
        layer_idx = None
        
        for part in group[0].split("."):
            try:
                layer_idx = int(part)
                break
            except:
                continue
        if layer_idx is not None:
            speedup_rules[layer_idx] = pruner.pruned_heads[group_idx]

    pruner._unwrap_model()

    model.bert._prune_heads(speedup_rules)

    model.config.pruned_heads =  {key: list(val) for key, val in pruner.pruned_heads.items()}

    return model


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] ...",
        description="Create, optimize and quantize Bert based model in ONNX."
    )
    parser.add_argument(
        "--version", action="version",
        version = f"{parser.prog} version 1.0.0"
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--encoder", action='store_true', help="If the model is for encoding or not. Must be BERT based."
    )
    group.add_argument(
        "--rerank", action='store_true', help="If the model is for encoding or not. Must be BERT based."
    )

    requiredNamed = parser.add_argument_group('required arguments')

    requiredNamed.add_argument(
        "--model", type=pathlib.Path, help="The HuggingFace model to use for reranking or encoding. Must be BERT based.", required=True
    )
    requiredNamed.add_argument(
        "--output", type=pathlib.Path, help="Folder where to save the ONNX model.", required=True
    )
    
    return parser


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
    )

    parser = init_argparse()
    args = parser.parse_args()

    if args.encoder:
        encoder = prune_encoder(args.model)
        onnx_encoder = convert_to_onnx(encoder, args.output, True)
        onnx_optimized_encoder = optimizing_model(onnx_encoder)

        quantizing_model(onnx_optimized_encoder)

    if args.rerank:
        rerank = prune_rerank(args.model)
        onnx_rerank = convert_to_onnx(rerank, args.output, False)
        onnx_optimized_rerank = optimizing_model(onnx_rerank)

        quantizing_model(onnx_optimized_rerank)


if __name__ == "__main__":
    main()