gcloud init
gcloud auth application-default login
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update


##### optimization

python scripts/get_models.py
python -m onnxruntime.transformers.optimizer --input onnx/encoder/model_shape_infer.onnx --output onnx/encoder/model_opt.onnx --model_type bert --float16 --use_gpu --input_int32
python -m onnxruntime.transformers.compare_bert_results --baseline_model onnx/encoder/model.onnx --optimized_model onnx/encoder/model_shape_infer.onnx --input_ids input_ids --input_mask attention_mask --batch_size 1 --sequence_length 128 --samples 100 --use_gpu  --atol 5e-4
python -m onnxruntime.transformers.bert_perf_test --model onnx/encoder/model_opt.onnx -b 1 -s 128 -t 100 --input_ids_name input_ids --input_mask_name attention_mask --use_gpu --opt_level 99

python -m onnxruntime.transformers.optimizer --input onnx/rerank/model_shape_infer.onnx --output onnx/rerank/model_opt.onnx --model_type bert --float16 --use_gpu --input_int32
python -m onnxruntime.transformers.compare_bert_results --baseline_model onnx/rerank/model.onnx --optimized_model onnx/rerank/model_shape_infer.onnx --input_ids input_ids --segment_ids token_type_ids --input_mask attention_mask --batch_size 1 --sequence_length 128 --samples 100 --use_gpu --atol 4e-2
python -m onnxruntime.transformers.bert_perf_test --model onnx/rerank/model_opt.onnx -b 1 -s 128 -t 100 --input_ids_name input_ids --input_mask_name attention_mask --segment_ids token_type_ids --use_gpu --opt_level 99







