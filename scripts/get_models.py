from collections import OrderedDict
from pathlib import Path
from typing import Mapping

import torch

from transformers import BertModel, AutoTokenizer, AutoConfig, AutoModelForSequenceClassification
from transformers.onnx import OnnxConfig, export, validate_model_outputs

from nni.algorithms.compression.pytorch.pruning import TransformerHeadPruner

from onnxruntime.transformers.fusion_options import FusionOptions
from onnxruntime.transformers.optimizer import optimize_model
from onnxruntime.quantization import quantize_dynamic, QuantType


class Encoder(BertModel):
    def __init__(self, config):
        super().__init__(config)

        self.sentence_embedding = torch.nn.Identity()
    
    def forward(self, input_ids, attention_mask, token_type_ids):
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


config = AutoConfig.from_pretrained("MODEL/NAME")
model = Encoder(config=config).from_pretrained("MODEL/NAME")
attention_name_groups = list(zip(["encoder.layer.{}.attention.self.query".format(i) for i in range(6)],
                                 ["encoder.layer.{}.attention.self.key".format(i) for i in range(6)],
                                 ["encoder.layer.{}.attention.self.value".format(i) for i in range(6)],
                                 ["encoder.layer.{}.attention.output.dense".format(i) for i in range(6)]))

kwargs = {"head_hidden_dim": 64,
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
}]

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
tokenizer = AutoTokenizer.from_pretrained("MODEL/NAME")
onnx_config = EncoderOnnxConfig(model.config)
output = Path("onnx/encoder/model.onnx")

if not output.parent.exists():
    output.parent.mkdir(parents=True)

onnx_inputs, onnx_outputs = export(tokenizer, model, onnx_config, 12, output)

validate_model_outputs(onnx_config, tokenizer, model, output, onnx_outputs, 1e-4)

optimization_options = FusionOptions('MODEL-TYPE')

optimization_options.enable_embed_layer_norm = False

optimizer = optimize_model("onnx/encoder/model.onnx",
                           "MODEL-TYPE",
                           0,
                           0,
                           opt_level=None,
                           optimization_options=optimization_options,
                           use_gpu=False,
                           only_onnxruntime=True)

optimizer.save_model_to_file("onnx/encoder/model_opt.onnx", False)

quantize_dynamic("onnx/encoder/model_opt.onnx", "onnx/encoder/model_opt_quant.onnx", weight_type=QuantType.QInt8, reduce_range=True)

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


config = AutoConfig.from_pretrained("MODEL/NAME")
model = AutoModelForSequenceClassification.from_pretrained("MODEL/NAME")

attention_name_groups = list(zip(["bert.encoder.layer.{}.attention.self.query".format(i) for i in range(6)],
                                 ["bert.encoder.layer.{}.attention.self.key".format(i) for i in range(6)],
                                 ["bert.encoder.layer.{}.attention.self.value".format(i) for i in range(6)],
                                 ["bert.encoder.layer.{}.attention.output.dense".format(i) for i in range(6)]))

kwargs = {"head_hidden_dim": 64,
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
}]

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

tokenizer = AutoTokenizer.from_pretrained("MODEL/NAME")
onnx_config = RerankOnnxConfig(model.config)
output = Path("onnx/rerank/model.onnx")

if not output.parent.exists():
    output.parent.mkdir(parents=True)

onnx_inputs, onnx_outputs = export(tokenizer, model, onnx_config, 12, output)

validate_model_outputs(onnx_config, tokenizer, model, output, onnx_outputs, 1e-4)

optimization_options = FusionOptions('MODEL-TYPE')

optimization_options.enable_embed_layer_norm = False

optimizer = optimize_model("onnx/rerank/model.onnx",
                           "MODEL-TYPE",
                           0,
                           0,
                           opt_level=None,
                           optimization_options=optimization_options,
                           use_gpu=False,
                           only_onnxruntime=True)

optimizer.save_model_to_file("onnx/rerank/model_opt.onnx", False)

quantize_dynamic("onnx/rerank/model_opt.onnx", "onnx/rerank/model_opt_quant.onnx", weight_type=QuantType.QInt8, reduce_range=True)
