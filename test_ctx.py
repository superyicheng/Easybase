import os
import shutil
import tempfile
import ctx

def test_init_creates_structure(monkeypatch):
    temp_dir = tempfile.mkdtemp()

    # 模拟所有 input
    inputs = iter([
        "1",                    # create new soul.md
        "Test KB",              # knowledge base name
        "Test description",     # description
        "1",                    # storage mode
        "",                     # default max_top_k
        "1",                    # enforcement off
        "1"                     # no scan
    ])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    try:
        ctx.cmd_init(base_dir=temp_dir)

        assert os.path.exists(os.path.join(temp_dir, "chunks"))
        assert os.path.exists(os.path.join(temp_dir, "knowledge"))
        assert os.path.exists(os.path.join(temp_dir, "logs"))
        assert os.path.exists(os.path.join(temp_dir, "config.yaml"))
        assert os.path.exists(os.path.join(temp_dir, "soul.md"))

    finally:
        shutil.rmtree(temp_dir)