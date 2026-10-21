"""静态语法与内存指标检查；不打开监听端口或发出请求。"""
import ast
import importlib.util
import pathlib
import tomllib
import xml.etree.ElementTree as ET

root = pathlib.Path(__file__).resolve().parents[1]
for path in root.rglob("*"):
    if "records" in path.parts or not path.is_file():
        continue
    if path.suffix == ".py":
        ast.parse(path.read_text(), filename=str(path))
    elif path.suffix == ".toml" or path.name == "Cargo.lock":
        tomllib.loads(path.read_text())
    elif path.suffix in (".xml", ".csproj") or path.name == "NuGet.Config":
        ET.parse(path)
spec = importlib.util.spec_from_file_location("probe", root / "08/probe.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
measurements = module.Measurements()
assert 'status="200"} 0' in measurements.render()
measurements.record(200, 0.05)
measurements.record(500, 2.0)
rendered = measurements.render()
assert 'status="200"} 1' in rendered
assert 'status="500"} 1' in rendered
assert 'le="0.1"} 1' in rendered
assert 'le="+Inf"} 2' in rendered
assert "http_request_duration_seconds_count 2" in rendered
print("PASS Python/TOML/XML语法、真实采样计数/直方图内存检查；无监听/请求")
