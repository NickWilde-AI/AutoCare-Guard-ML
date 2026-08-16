# 本地环境问题根因说明

## 问题现象

通过当前虚拟环境运行项目命令时，Python 会在项目代码真正加载前失败：

```bash
make compile
make summary
```

两个命令都会在 Python 启动阶段报错：

```text
Fatal Python error: init_import_site: Failed to import the site module
UnicodeDecodeError: 'ascii' codec can't decode byte 0xe6 ...
```

早期还遇到过：

```bash
python3 -m pytest -q
```

无法执行测试的问题，原因是当时没有安装开发依赖。当前仓库已经在 `pyproject.toml` 声明了 `dev` extra，推荐用 `pip install -e ".[dev,serve]"` 建环境。

## 根因

当前 shell 环境把 locale 强制成了 ASCII：

```text
LC_ALL="C"
LC_CTYPE="C"
```

而项目路径里包含中文字符，例如：

```text
.../文稿/.../AI-IM-Guard-ML
```

项目已经以 editable install 的方式安装到 `.venv`，这个绝对路径被写入了：

```text
.venv/lib/python3.11/site-packages/__editable__.ai_im_guard_ml-0.1.0.pth
```

Python 启动时会由 `site` 模块读取 `.pth` 文件。由于 `LC_ALL=C`，Python 会按 ASCII 解码路径；当它遇到路径里的中文字符字节时，就会触发 `UnicodeDecodeError`。因此错误发生在 Python 启动阶段，而不是项目代码、CLI 或测试逻辑本身。

## 验证结果

下面这个命令会失败：

```bash
make compile
```

显式指定 UTF-8 locale 后可以成功：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 make compile
```

同样，项目 demo 摘要命令也可以成功：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 make summary
```

实际输出如下：

```json
{
  "total": 3,
  "by_source": {
    "demo": 3
  },
  "by_topic": {
    "无主题": 1,
    "代刷/包榜": 1,
    "诈骗引流": 1
  },
  "by_label": {
    "not_exist_violation": 1,
    "exist_violation": 2
  }
}
```

这说明项目主链路本身可以运行，当前卡点主要是本地 shell 的编码环境。

## 立即 unblock 方案

临时运行命令时，加上 UTF-8 locale：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 make summary
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 make compile
```

如果希望长期生效，可以把下面两行加入 shell 配置文件，例如 `~/.zshrc`：

```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

然后重新打开终端，再执行：

```bash
make compile
make summary
```

## 后续建议

仓库已经声明开发依赖，推荐新环境直接安装：

```bash
pip install -e ".[dev,serve]"
```

之后可以使用：

```bash
make test
make enterprise-check
```
