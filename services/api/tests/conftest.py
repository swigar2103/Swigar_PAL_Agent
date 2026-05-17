import os

# Avoid Chroma/onnx dependency failures in CI and local test runs without GPU/DLL.
os.environ.setdefault("SWIGAR_MEMORY_DISABLED", "1")
