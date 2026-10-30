# engine-dlls —— 引擎运行期 DLL（随 clone 一起下来）

NInfer 引擎在 Windows 上要 6 个 DLL，官方 Release **不带**，而且其中 5 个 FFmpeg + 1 个 libcurl 的上游（BtbN/FFmpeg-Builds、curl.se）都是滚动的 `latest`：今天重下拿到的是另一个 commit 编的字节数。本目录是**按哈希冻结**的那一份，`RESTORE.md` §3.3 里那 6 行 SHA-256 只对得上这里的文件。

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `avcodec-63.dll` | 91,810,816 | `1ab43ac33e92aad9f29e82e6b4f57e06ff3537097d71908786d1388a6032ea45` |
| `avformat-63.dll` | 23,003,136 | `1082bdcb0fd3bb62205a2be123350f2f4fa67a1478bb0162989d65c1463d29ef` |
| `avutil-61.dll` | 3,025,408 | `aabe139afdf6c3277d490faddaac739c8ed616739bd9287cd53a7a56ba919022` |
| `swscale-10.dll` | 2,343,936 | `c10c48b8003ed5730b3ece95009a2db5c5e49c40c0a0b07c3b305ddc7fcc01f4` |
| `swresample-7.dll` | 747,008 | `dc8594e1c7cc627a2f2a1510c98a6b823a8dff95455684aafcfd3514dc12eb93` |
| `libcurl-x64.dll` | 3,722,344 | `d8bfa3e3ed29c29dc4db02afda0355f4a67990e93a3a4ecb089bf09a6071131d` |

合计 124,652,648 B（118.9 MiB）。校验：`cd engine-dlls && sha256sum -c SHA256SUMS.txt`。

## 怎么用

```bash
# 克隆下来就有，直接铺进 engine/（与 ninfer-serve-89.exe 同目录）
cp engine-dlls/*.dll engine/
python tools/restore_check.py --deep      # 应报 18/18 OK
```

另外三个 CUDA DLL（`cudart64_13` / `cublas64_13` / `cublasLt64_13`）**不在这里**，从 PyPI 精确重装即可：

```bash
pip download nvidia-cuda-runtime==13.3.29 --only-binary=:all: --python-version 3.12 --platform win_amd64
pip download nvidia-cublas==13.5.1.27        --only-binary=:all: --python-version 3.12 --platform win_amd64
# ⚠ 不要写 nvidia-cuda-runtime-cu13 / nvidia-cublas-cu13 —— 那是 DEPRECATED 空壳包
```

## 出处与许可

- FFmpeg 五个：BtbN/FFmpeg-Builds `ffmpeg-n9.0-latest-win64-lgpl-shared` → **LGPL-3.0**（https://github.com/BtbN/FFmpeg-Builds ，源码 https://ffmpeg.org/download.html ）
- `libcurl-x64.dll`：curl.se 官方 Win64 构建 `curl-8.23.0_6-win64-mingw` → curl 许可（https://curl.se/docs/copyright.html ）

原样分发、未做任何修改。同一份字节也挂在 Release <https://github.com/zkkk9555/local_model/releases/tag/dlls-20261031>（给只想拿 DLL、不想 clone 的人）。