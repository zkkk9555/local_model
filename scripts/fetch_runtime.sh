
set -u
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
cd /c/Users/Administrator/Documents/deepseek-harness/default-workspace
mkdir -p dl runtime
get() {
  url="$1"; out="$2"
  if [ -s "$out" ]; then echo "SKIP existing $out"; return 0; fi
  echo "GET $url"
  curl -L --fail --retry 4 --retry-delay 4 -m 1800 -A "$UA" -o "$out" "$url"
  echo "  exit=$? size=$(stat -c %s "$out" 2>/dev/null)"
}
get "https://developer.download.nvidia.com/compute/cuda/redist/cuda_cudart/windows-x86_64/cuda_cudart-windows-x86_64-13.3.29-archive.zip" dl/cudart.zip
get "https://developer.download.nvidia.com/compute/cuda/redist/libcublas/windows-x86_64/libcublas-windows-x86_64-13.5.1.27-archive.zip" dl/cublas.zip
get "https://curl.se/windows/dl-8.23.0_6/curl-8.23.0_6-win64-mingw.zip" dl/curl.zip
get "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip" dl/ffmpeg.zip
echo "=== all downloads done ==="
echo "--- cudart ---"
python scripts/zip_extract.py dl/cudart.zip runtime 'cudart64_13.dll'
echo "--- cublas ---"
python scripts/zip_extract.py dl/cublas.zip runtime 'cublas64_13.dll' 'cublasLt64_13.dll'
echo "--- curl ---"
python scripts/zip_extract.py dl/curl.zip runtime 'libcurl*.dll'
echo "--- ffmpeg ---"
python scripts/zip_extract.py dl/ffmpeg.zip runtime 'avcodec-*.dll' 'avformat-*.dll' 'avutil-*.dll' 'swscale-*.dll' 'swresample-*.dll'
echo "--- avail in ffmpeg zip (if mismatch) ---"
python - <<'EOF'
import zipfile
try:
    z=zipfile.ZipFile('dl/ffmpeg.zip')
    names=sorted({n.split('/')[-1] for n in z.namelist() if n.lower().endswith('.dll')})
    print('\n'.join(names[:60]))
except Exception as e:
    print('ERR', e)
EOF
ls -l runtime/
