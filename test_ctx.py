import ctx
import pytest


def mock_init(monkeypatch):
    """
    Helper: mock interactive input for cmd_init
    """
    inputs = iter([
        "1",        # create new soul.md
        "Test KB",  # knowledge base name
        "Test description",
        "1",        # storage mode
        "",         # default max_top_k
        "1",        # enforcement off
        "1"         # no scan
    ])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))


def test_init_creates_structure(monkeypatch, tmp_path):
    base_dir = str(tmp_path)

    mock_init(monkeypatch)
    ctx.cmd_init(base_dir=base_dir)

    assert (tmp_path / "chunks").exists()
    assert (tmp_path / "knowledge").exists()
    assert (tmp_path / "logs").exists()
    assert (tmp_path / "config.yaml").exists()
    assert (tmp_path / "soul.md").exists()


def test_add_and_search(monkeypatch, tmp_path):
    base_dir = str(tmp_path)

    mock_init(monkeypatch)
    ctx.cmd_init(base_dir=base_dir)

    ctx.cmd_add([
        "--id", "chunk1",
        "--summary", "BM25 test summary",
        "--body", "This is a BM25 body content"
    ], base_dir=base_dir)

    index = ctx.load_index(base_dir=base_dir)
    results = ctx.search("BM25", index)

    assert len(results) > 0
    assert results[0]["id"] == "chunk1"


def test_bm25_ranking(monkeypatch, tmp_path):
    base_dir = str(tmp_path)

    mock_init(monkeypatch)
    ctx.cmd_init(base_dir=base_dir)

    ctx.cmd_add([
        "--id", "chunk1",
        "--summary", "strong",
        "--body", "BM25 BM25 BM25"
    ], base_dir=base_dir)

    ctx.cmd_add([
        "--id", "chunk2",
        "--summary", "weak",
        "--body", "BM25"
    ], base_dir=base_dir)

    index = ctx.load_index(base_dir=base_dir)
    results = ctx.search("BM25", index)

    assert results[0]["id"] == "chunk1"


def test_top_k_limit(monkeypatch, tmp_path):
    base_dir = str(tmp_path)

    mock_init(monkeypatch)
    ctx.cmd_init(base_dir=base_dir)

    for i in range(5):
        ctx.cmd_add([
            "--id", f"chunk{i}",
            "--summary", f"summary {i}",
            "--body", "BM25"
        ], base_dir=base_dir)

    index = ctx.load_index(base_dir=base_dir)
    results = ctx.search("BM25", index, top_k=2)

    assert len(results) == 2


def test_no_results(monkeypatch, tmp_path):
    base_dir = str(tmp_path)

    mock_init(monkeypatch)
    ctx.cmd_init(base_dir=base_dir)

    # 添加一个不相关 chunk（保证 index.json 被生成）
    ctx.cmd_add([
        "--id", "dummy",
        "--summary", "nothing related",
        "--body", "irrelevant content"
    ], base_dir=base_dir)

    index = ctx.load_index(base_dir=base_dir)
    results = ctx.search("nonexistentterm", index)

    assert results == []

    #hanson 留言：诚哥这串test代码只跑成功了一个，我设置了5个，按理来说应该能collet 5份数据的，
    #但是只收集到了一份，我是那GPT写的，因为我还没法链接codex与repo。我可以自己fork一份你的到我的
    #库里，但是那样会麻烦很多...总之看你了，我这些段落都是gpt生成的，你可以让你的AI再检查检查
    