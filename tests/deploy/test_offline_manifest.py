import subprocess, pathlib

def test_bundle_script_lists_all_images(tmp_path):
    # dry-run 模式只打印将打包的镜像清单，不真正 docker save
    out = subprocess.run(
        ["bash", "scripts/offline_bundle.sh", "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    for img in ["apache/age", "temporalio/auto-setup", "ollama/ollama"]:
        assert img in out.stdout
    # 模型权重清单需含三件套
    for w in ["qwen3", "embedding", "reranker"]:
        assert w in out.stdout.lower()
